using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

namespace JaneConverterLauncher
{
    static class Program
    {
        [STAThread]
        static void Main(string[] args)
        {
            try
            {
                string baseDir = AppDomain.CurrentDomain.BaseDirectory;
                string runtimeDir = ResolveRuntimeDirectory(baseDir);
                string desktopUiPath = Path.Combine(runtimeDir, "JaneConverterDesktop.exe");
                string nativeUiPath = Path.Combine(runtimeDir, "JaneConverterNative.exe");
                bool forceLegacy = HasArgument(args, "--legacy-python");
                bool forceTauri = HasArgument(args, "--tauri");
                bool forceRust = HasArgument(args, "--rust");
                if (!HasArgument(args, "--skip-pending-update"))
                {
                    TrySchedulePendingUpdate(runtimeDir);
                }
                string preference = ReadFrontendPreference(baseDir);

                // Tauri is the default when its bundled executable is present.
                // The existing Rust and Python surfaces remain reversible fallbacks.
                if (!forceLegacy && !forceRust && (forceTauri || string.Equals(preference, "tauri", StringComparison.OrdinalIgnoreCase)) && File.Exists(desktopUiPath))
                {
                    StartChild(desktopUiPath, string.Empty, runtimeDir, baseDir);

                    return;
                }

                if (!forceLegacy && (forceRust || string.Equals(preference, "rust", StringComparison.OrdinalIgnoreCase)) && File.Exists(nativeUiPath))
                {
                    StartChild(nativeUiPath, string.Empty, runtimeDir, baseDir);

                    return;
                }

                if (!forceLegacy && !forceTauri && !forceRust && string.Equals(preference, "tauri", StringComparison.OrdinalIgnoreCase) && File.Exists(nativeUiPath))
                {
                    StartChild(nativeUiPath, string.Empty, runtimeDir, baseDir);

                    return;
                }

                string scriptPath = Path.Combine(runtimeDir, "gui.py");

                if (!File.Exists(scriptPath))
                {
                    MessageBox.Show(
                        "Could not find 'gui.py' in the application directory:\n" + baseDir,
                        "JaneConverter - File Missing",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error
                    );
                    return;
                }

                // Locate Python executable (check local venv first, then system path)
                string pythonExe = "pythonw.exe";
                string[] candidatePaths = new string[]
                {
                    Path.Combine(runtimeDir, "venv", "Scripts", "pythonw.exe"),
                    Path.Combine(runtimeDir, ".venv", "Scripts", "pythonw.exe"),
                    Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Python", "Python312", "pythonw.exe"),
                    Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Python", "Python311", "pythonw.exe"),
                    @"C:\Python314\pythonw.exe",
                    @"C:\Python312\pythonw.exe",
                    @"C:\Python311\pythonw.exe",
                    @"C:\Python310\pythonw.exe"
                };

                foreach (string candidate in candidatePaths)
                {
                    if (File.Exists(candidate))
                    {
                        pythonExe = candidate;
                        break;
                    }
                }

                StartChild(pythonExe, Quote(scriptPath), runtimeDir, baseDir);

            }
            catch (System.ComponentModel.Win32Exception)
            {
                MessageBox.Show(
                    "Python runtime was not found on your computer.\n\n" +
                    "To launch JaneConverter, please run 'setup.bat' in this folder to install dependencies automatically, " +
                    "or install Python 3.10+ from https://www.python.org/downloads/ (check 'Add to PATH').",
                    "JaneConverter - Python Not Found",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning
                );
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    "An error occurred while launching JaneConverter:\n\n" + ex.Message,
                    "JaneConverter Launch Error",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
            }
        }

        static string ResolveRuntimeDirectory(string launcherDir)
        {
            if (HasRuntimeExecutables(launcherDir))
            {
                return launcherDir;
            }

            string distDir = Path.Combine(launcherDir, "dist");
            if (Directory.Exists(distDir))
            {
                string[] candidates = Directory.GetDirectories(distDir, "JaneConverter-*");
                Array.Sort(candidates, StringComparer.OrdinalIgnoreCase);
                for (int index = candidates.Length - 1; index >= 0; index--)
                {
                    if (HasRuntimeExecutables(candidates[index]))
                    {
                        return candidates[index];
                    }
                }
            }

            return launcherDir;
        }

        static bool HasRuntimeExecutables(string directory)
        {
            return File.Exists(Path.Combine(directory, "JaneConverterDesktop.exe")) ||
                   File.Exists(Path.Combine(directory, "JaneConverterNative.exe"));
        }
        static string SharedDataRoot(string baseDir)
        {
            string configured = Environment.GetEnvironmentVariable("JANECONVERTER_DATA_DIR");
            if (!string.IsNullOrWhiteSpace(configured))
            {
                return Path.GetFullPath(configured);
            }
            return baseDir;
        }

        static void StartChild(string fileName, string arguments, string workingDirectory, string dataRoot)
        {
            ProcessStartInfo info = new ProcessStartInfo
            {
                FileName = fileName,
                Arguments = arguments ?? string.Empty,
                WorkingDirectory = workingDirectory,
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden
            };
            info.EnvironmentVariables["JANECONVERTER_DATA_DIR"] = SharedDataRoot(dataRoot);
            Process.Start(info);
        }
        static bool HasArgument(string[] args, string expected)
        {
            foreach (string arg in args ?? new string[0])
            {
                if (string.Equals(arg, expected, StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }
            }
            return false;
        }

        static string ReadFrontendPreference(string baseDir)
        {
            string configured = Environment.GetEnvironmentVariable("JANECONVERTER_DATA_DIR");
            string[] candidates = new string[]
            {
                string.IsNullOrWhiteSpace(configured) ? null : Path.Combine(configured, "frontend.preference"),
                Path.Combine(baseDir, "frontend.preference"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "JaneConverter", "frontend.preference")
            };
            foreach (string candidate in candidates)
            {
                try
                {
                    if (!File.Exists(candidate))
                    {
                        continue;
                    }
                    string value = File.ReadAllText(candidate).Trim();
                    if (string.Equals(value, "python", StringComparison.OrdinalIgnoreCase) ||
                        string.Equals(value, "rust", StringComparison.OrdinalIgnoreCase) ||
                        string.Equals(value, "tauri", StringComparison.OrdinalIgnoreCase))
                    {
                        return value;
                    }
                }
                catch (IOException)
                {
                    // A locked preference must never prevent the application from launching.
                }
            }
            return "tauri";
        }

        static void TrySchedulePendingUpdate(string baseDir)
        {
            string configured = Environment.GetEnvironmentVariable("JANECONVERTER_DATA_DIR");
            string[] manifests = new string[]
            {
                string.IsNullOrWhiteSpace(configured) ? null : Path.Combine(configured, "updates", "pending.json"),
                Path.Combine(baseDir, "updates", "pending.json"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "JaneConverter", "updates", "pending.json")
            };
            bool pending = false;
            foreach (string manifest in manifests)
            {
                if (!string.IsNullOrWhiteSpace(manifest) && File.Exists(manifest))
                {
                    pending = true;
                    break;
                }
            }
            if (!pending)
            {
                return;
            }

            string helper = Path.Combine(baseDir, "update_helper.py");
            if (!File.Exists(helper))
            {
                return;
            }
            string python = FindPython(baseDir);
            try
            {
                StartChild(python, Quote(helper) + " " + Quote(baseDir) + " " + Process.GetCurrentProcess().Id.ToString(), baseDir, baseDir);

                Environment.Exit(0);
            }
            catch (Win32Exception)
            {
                // Continue launching the existing app when the optional
                // updater cannot start; the manifest remains available.
            }
        }

        static string FindPython(string baseDir)
        {
            string[] candidates = new string[]
            {
                Path.Combine(baseDir, "venv", "Scripts", "python.exe"),
                Path.Combine(baseDir, ".venv", "Scripts", "python.exe"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Python", "Python312", "python.exe"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Python", "Python311", "python.exe"),
                @"C:\Python314\python.exe", @"C:\Python312\python.exe", @"C:\Python311\python.exe", @"C:\Python310\python.exe"
            };
            foreach (string candidate in candidates)
            {
                if (File.Exists(candidate)) return candidate;
            }
            return "python.exe";
        }

        static string Quote(string value)
        {
            return "\"" + (value ?? string.Empty).Replace("\\\"", "\\\\\"") + "\"";
        }
    }
}
