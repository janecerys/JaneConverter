using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

namespace JaneConverterLauncher
{
    static class Program
    {
        [STAThread]
        static void Main()
        {
            try
            {
                string baseDir = AppDomain.CurrentDomain.BaseDirectory;
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
    }
}
