using System;
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
            string[] candidates = new string[]
            {
                Path.Combine(baseDir, "frontend.preference"),
                Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "JaneConverter",
                    "frontend.preference")
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
    }
}
