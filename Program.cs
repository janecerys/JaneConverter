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
                string nativeUiPath = Path.Combine(baseDir, "JaneConverterNative.exe");
                bool forceLegacy = HasArgument(args, "--legacy-python");
                bool forceRust = HasArgument(args, "--rust");
                if (!HasArgument(args, "--skip-pending-update"))
                {
                    TrySchedulePendingUpdate(baseDir);
                }
                string preference = ReadFrontendPreference(baseDir);

                // Rust is the default. The preference and explicit command-line
                // switches keep the original Python interface available as a
                // reversible recovery path.
                if (!forceLegacy && (forceRust || !string.Equals(preference, "python", StringComparison.OrdinalIgnoreCase)) && File.Exists(nativeUiPath))
                {
                    Process.Start(new ProcessStartInfo
                    {
                        FileName = nativeUiPath,
                        WorkingDirectory = baseDir,
                        UseShellExecute = true,
                        CreateNoWindow = true,
                        WindowStyle = ProcessWindowStyle.Hidden
                    });
                    return;
                }

                string scriptPath = Path.Combine(baseDir, "gui.py");

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
                    Path.Combine(baseDir, "venv", "Scripts", "pythonw.exe"),
                    Path.Combine(baseDir, ".venv", "Scripts", "pythonw.exe"),
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

                ProcessStartInfo psi = new ProcessStartInfo
                {
                    FileName = pythonExe,
                    Arguments = "\"" + scriptPath + "\"",
                    WorkingDirectory = baseDir,
                    UseShellExecute = true,
                    CreateNoWindow = true,
                    WindowStyle = ProcessWindowStyle.Hidden
                };

                Process.Start(psi);
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
                        string.Equals(value, "rust", StringComparison.OrdinalIgnoreCase))
                    {
                        return value;
                    }
                }
                catch (IOException)
                {
                    // A locked preference must never prevent the application from launching.
                }
            }
            return "rust";
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
                Process.Start(new ProcessStartInfo
                {
                    FileName = python,
                    Arguments = Quote(helper) + " " + Quote(baseDir) + " " + Process.GetCurrentProcess().Id.ToString(),
                    WorkingDirectory = baseDir,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    WindowStyle = ProcessWindowStyle.Hidden
                });
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
