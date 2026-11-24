using System;
using System.Diagnostics;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Threading;
using LibreHardwareMonitor.Hardware;

namespace OledSensors
{
    internal static class Program
    {
        [DllImport("kernel32.dll")]
        private static extern bool SetProcessWorkingSetSize(IntPtr hProcess, IntPtr min, IntPtr max);

        private static void TrimMemory()
        {
            try
            {
                GC.Collect(2, GCCollectionMode.Forced, true);
                GC.WaitForPendingFinalizers();
                SetProcessWorkingSetSize(Process.GetCurrentProcess().Handle, (IntPtr)(-1), (IntPtr)(-1));
            }
            catch { }
        }

        private static int Main(string[] args)
        {
            int intervalMs = 1000;
            bool enableGpu = true;
            foreach (string a in args)
            {
                if (a == "--no-gpu")
                {
                    enableGpu = false;
                    continue;
                }
                int parsed;
                if (int.TryParse(a, out parsed) && parsed >= 250 && parsed <= 10000)
                {
                    intervalMs = parsed;
                }
            }

            var stdinWatcher = new Thread(() =>
            {
                try
                {
                    while (Console.Read() != -1) { }
                }
                catch { }
                Environment.Exit(0);
            });
            stdinWatcher.IsBackground = true;
            stdinWatcher.Start();

            Computer computer = null;
            try
            {
                computer = new Computer
                {
                    IsCpuEnabled = true,
                    IsGpuEnabled = enableGpu
                };
                computer.Open();
            }
            catch (Exception ex)
            {
                Console.WriteLine("{\"cpu_temp\":null,\"gpu_temp\":null,\"gpu_load\":null,\"error\":\"" + Escape(ex.Message) + "\"}");
                Console.Out.Flush();
                Thread.Sleep(Timeout.Infinite);
                return 1;
            }

            IHardware cpuHw = null;
            ISensor cpuTempSensor = null;
            IHardware gpuHw = null;
            ISensor gpuTempSensor = null;
            ISensor gpuLoadSensor = null;

            int ticks = 0;
            while (true)
            {
                float? cpuTemp = null;
                float? gpuTemp = null;
                float? gpuLoad = null;

                try
                {
                    if (cpuHw == null)
                    {
                        int cpuPriority = 99;
                        foreach (IHardware hw in computer.Hardware)
                        {
                            if (hw.HardwareType == HardwareType.Cpu)
                            {
                                cpuHw = hw;
                                hw.Update();
                                foreach (ISensor s in hw.Sensors)
                                {
                                    if (s.SensorType == SensorType.Temperature && s.Value.HasValue && s.Value.Value > 0 && s.Value.Value < 150)
                                    {
                                        string name = (s.Name ?? "").ToLowerInvariant();
                                        int prio = 50;
                                        if (name.Contains("tctl") || name.Contains("tdie")) prio = 1;
                                        else if (name.Contains("package")) prio = 2;
                                        else if (name.Contains("core average") || name.Contains("core max")) prio = 3;
                                        else if (name.Contains("cpu")) prio = 4;

                                        if (prio < cpuPriority)
                                        {
                                            cpuPriority = prio;
                                            cpuTempSensor = s;
                                        }
                                    }
                                }
                            }
                            else if (enableGpu && gpuHw == null && (hw.HardwareType == HardwareType.GpuNvidia || hw.HardwareType == HardwareType.GpuAmd || hw.HardwareType == HardwareType.GpuIntel))
                            {
                                gpuHw = hw;
                                hw.Update();
                                foreach (ISensor s in hw.Sensors)
                                {
                                    string name = (s.Name ?? "").ToLowerInvariant();
                                    if (s.SensorType == SensorType.Temperature && (name.Contains("core") || name.Contains("gpu")))
                                    {
                                        if (gpuTempSensor == null) gpuTempSensor = s;
                                    }
                                    else if (s.SensorType == SensorType.Load && (name.Contains("core") || name.Contains("gpu")))
                                    {
                                        if (gpuLoadSensor == null) gpuLoadSensor = s;
                                    }
                                }
                            }
                        }
                    }

                    if (cpuHw != null)
                    {
                        cpuHw.Update();
                        if (cpuTempSensor != null && cpuTempSensor.Value.HasValue)
                        {
                            cpuTemp = cpuTempSensor.Value.Value;
                        }
                    }

                    if (enableGpu && gpuHw != null)
                    {
                        gpuHw.Update();
                        if (gpuTempSensor != null && gpuTempSensor.Value.HasValue) gpuTemp = gpuTempSensor.Value.Value;
                        if (gpuLoadSensor != null && gpuLoadSensor.Value.HasValue) gpuLoad = gpuLoadSensor.Value.Value;
                    }
                }
                catch { }

                Console.WriteLine(
                    "{\"cpu_temp\":" + Fmt(cpuTemp) +
                    ",\"gpu_temp\":" + Fmt(gpuTemp) +
                    ",\"gpu_load\":" + Fmt(gpuLoad) + "}"
                );
                Console.Out.Flush();

                if (ticks == 0 || ticks % 60 == 0)
                {
                    TrimMemory();
                }
                ticks++;
                Thread.Sleep(intervalMs);
            }
        }

        private static string Fmt(float? v)
        {
            return v.HasValue ? v.Value.ToString("0.0", CultureInfo.InvariantCulture) : "null";
        }

        private static string Escape(string s)
        {
            return (s ?? "").Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", " ").Replace("\n", " ");
        }
    }
}
