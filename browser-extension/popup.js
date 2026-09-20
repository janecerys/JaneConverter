const connectButton = document.getElementById("connect");
const statusElement = document.getElementById("status");

function setStatus(message, kind = "") {
  statusElement.textContent = message;
  statusElement.className = kind;
}

async function findAccessTabs() {
  const tabs = await chrome.tabs.query({});
  return tabs
    .filter((tab) => {
    if (!tab.url) return false;
    try {
      const url = new URL(tab.url);
      return (url.hostname === "127.0.0.1" || url.hostname === "localhost") && /^\/access\/[^/]+(?:\/ready)?\/?$/.test(url.pathname);
    } catch {
      return false;
    }
    })
    .sort((left, right) => Number(Boolean(right.active)) - Number(Boolean(left.active)));
}

function accessEndpoint(tab, suffix) {
  const url = new URL(tab.url);
  const match = url.pathname.match(/^\/access\/[^/]+/);
  if (!match) throw new Error("The JaneConverter access page is no longer open.");
  const accessPath = match[0];
  return `${url.origin}${accessPath}${suffix}`;
}

async function readJson(response) {
  const body = await response.text();
  try {
    return JSON.parse(body);
  } catch {
    const status = response.status ? ` (HTTP ${response.status})` : "";
    throw new Error(`JaneConverter returned an unexpected page${status}. This access tab may belong to an older launcher; rebuild or reopen JaneConverter, confirm a fresh access link, then try Connect again.`);
  }
}

async function requestSourcePermission(sourceUrl) {
  const source = new URL(sourceUrl);
  const origin = `${source.protocol}//${source.host}/*`;
  try {
    if (await chrome.permissions.contains({ origins: [origin] })) return true;
    const granted = await chrome.permissions.request({ origins: [origin] });
    return granted && await chrome.permissions.contains({ origins: [origin] });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error("Vivaldi could not grant access to " + source.host + ": " + message);
  }
}

function relatedHost(left, right) {
  return left === right || left.endsWith("." + right) || right.endsWith("." + left);
}

function cookieMatchesSource(cookie, source) {
  const cookieDomain = String(cookie.domain || "").toLowerCase().replace(/^\.+/, "");
  const sourceHost = source.hostname.toLowerCase();
  const domainMatches = cookie.hostOnly
    ? cookieDomain === sourceHost
    : sourceHost === cookieDomain || sourceHost.endsWith("." + cookieDomain);
  if (!domainMatches) return false;

  const cookiePath = cookie.path || "/";
  const sourcePath = source.pathname || "/";
  const pathMatches = cookiePath === "/"
    || sourcePath === cookiePath
    || sourcePath.startsWith(cookiePath.replace(/\/$/, "") + "/");
  return pathMatches && (!cookie.secure || source.protocol === "https:");
}

async function cookieStoreForTab(tabId) {
  if (typeof chrome.cookies.getAllCookieStores !== "function" || typeof tabId !== "number") return undefined;
  try {
    const stores = await chrome.cookies.getAllCookieStores();
    return stores.find((store) => store.tabIds?.includes(tabId))?.id;
  } catch {
    return undefined;
  }
}

async function partitionKeyForTab(tabId) {
  if (typeof chrome.cookies.getPartitionKey !== "function" || typeof tabId !== "number") return undefined;
  try {
    return await chrome.cookies.getPartitionKey({ tabId, frameId: 0 });
  } catch {
    return undefined;
  }
}

async function getCookies(details, storeId, partitionKey, optional = false) {
  const query = { ...details };
  if (storeId) query.storeId = storeId;
  if (partitionKey) query.partitionKey = partitionKey;
  try {
    return await chrome.cookies.getAll(query);
  } catch (error) {
    if (optional) return [];
    const message = error instanceof Error ? error.message : String(error);
    throw new Error("Vivaldi rejected cookie access: " + message);
  }
}

function cookieKey(cookie) {
  return [cookie.storeId, cookie.domain, cookie.path, cookie.name].join(":");
}

async function collectSourceCookies(sourceUrl) {
  const source = new URL(sourceUrl);
  const tabs = await chrome.tabs.query({});
  const sourceTabs = tabs
    .filter((tab) => {
      if (!tab.url) return false;
      try {
        return relatedHost(new URL(tab.url).hostname, source.hostname);
      } catch {
        return false;
      }
    })
    .sort((left, right) => Number(Boolean(right.active)) - Number(Boolean(left.active)));
  const sourceTab = sourceTabs[0];
  const storeId = await cookieStoreForTab(sourceTab?.id);
  const partitionKey = await partitionKeyForTab(sourceTab?.id);
  const storeIds = storeId ? [storeId, undefined] : [undefined];
  const queryUrls = new Set([source.href]);
  for (const tab of sourceTabs) queryUrls.add(tab.url);
  const cookies = new Map();
  let rawCookieCount = 0;
  let filteredCookieCount = 0;

  for (const candidateStoreId of storeIds) {
    for (const url of queryUrls) {
      const urlCookies = await getCookies({ url }, candidateStoreId, undefined, Boolean(candidateStoreId));
      rawCookieCount += urlCookies.length;
      for (const cookie of urlCookies) {
        if (cookieMatchesSource(cookie, source)) {
          filteredCookieCount += 1;
          cookies.set(cookieKey(cookie), cookie);
        }
      }
      if (partitionKey) {
        const partitionedCookies = await getCookies({ url }, candidateStoreId, partitionKey, true);
        rawCookieCount += partitionedCookies.length;
        for (const cookie of partitionedCookies) {
          if (cookieMatchesSource(cookie, source)) {
            filteredCookieCount += 1;
            cookies.set(cookieKey(cookie), cookie);
          }
        }
      }
    }
  }

  if (!cookies.size) {
    const domains = new Set([source.hostname]);
    const parentDomain = source.hostname.replace(/^[^.]+\./, "");
    if (parentDomain !== source.hostname) domains.add(parentDomain);
    for (const candidateStoreId of storeIds) {
      for (const domain of domains) {
        const domainCookies = await getCookies({ domain }, candidateStoreId, undefined, Boolean(candidateStoreId));
        rawCookieCount += domainCookies.length;
        for (const cookie of domainCookies) {
          if (cookieMatchesSource(cookie, source)) {
            filteredCookieCount += 1;
            cookies.set(cookieKey(cookie), cookie);
          }
        }
        if (partitionKey) {
          const partitionedCookies = await getCookies({ domain }, candidateStoreId, partitionKey, true);
          rawCookieCount += partitionedCookies.length;
          for (const cookie of partitionedCookies) {
            if (cookieMatchesSource(cookie, source)) {
              filteredCookieCount += 1;
              cookies.set(cookieKey(cookie), cookie);
            }
          }
        }
      }
    }
  }
  return {
    cookies: [...cookies.values()],
    rawCookieCount,
    filteredCookieCount,
    sourceTabCount: sourceTabs.length,
    storeId: storeId || "default",
    partitionedQuery: Boolean(partitionKey),
  };
}

async function connect() {
  connectButton.disabled = true;
  setStatus("Finding the confirmed JaneConverter access page...");
  try {
    const accessTabs = await findAccessTabs();
    if (!accessTabs.length) {
      throw new Error("Open and confirm the JaneConverter access link first.");
    }

    let accessTab = null;
    let challenge = null;
    let lastError = null;
    for (const candidateTab of accessTabs) {
      try {
        const challengeResponse = await fetch(accessEndpoint(candidateTab, "/bridge/challenge"), { cache: "no-store" });
        const candidateChallenge = await readJson(challengeResponse);
        if (!challengeResponse.ok) {
          lastError = new Error(candidateChallenge.error || "JaneConverter has not confirmed access yet.");
          continue;
        }
        accessTab = candidateTab;
        challenge = candidateChallenge;
        break;
      } catch (error) {
        lastError = error;
      }
    }
    if (!accessTab || !challenge) {
      throw lastError || new Error("Open and confirm the JaneConverter access link first.");
    }

    setStatus("Requesting permission for this source only...", "warning");
    if (!await requestSourcePermission(challenge.sourceUrl)) {
      throw new Error("The source permission was not approved.");
    }

    const collected = await collectSourceCookies(challenge.sourceUrl);
    if (!collected.cookies.length) {
      const sourceHost = new URL(challenge.sourceUrl).hostname;
      throw new Error(
        "No usable browser cookies were available for " + sourceHost
        + ". Vivaldi returned " + collected.rawCookieCount
        + " cookie(s); " + collected.filteredCookieCount
        + " matched the source. Tabs: " + collected.sourceTabCount
        + ", store: " + collected.storeId
        + ". Keep the source open and signed in in this Vivaldi profile, then retry."
      );
    }

    setStatus("Sending the source-scoped session to JaneConverter...");
    const bridgeResponse = await fetch(accessEndpoint(accessTab, "/bridge"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cookies: collected.cookies })
    });
    const result = await readJson(bridgeResponse);
    if (!bridgeResponse.ok) throw new Error(result.error || "JaneConverter rejected the browser session.");
    setStatus("Connected. Return to JaneConverter and convert while the browser stays open.");
  } catch (error) {
    setStatus(error instanceof Error ? error.message : String(error), "error");
  } finally {
    connectButton.disabled = false;
  }
}

connectButton.addEventListener("click", () => void connect());
