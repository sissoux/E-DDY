#!/usr/bin/env python3
# Licensed under CERN-OHL-S-2.0
# © 2025 ADSTech [e-ddy]

"""
flash_gui.py — E-DDY Board Flash Tool

GUI tool to automate flashing new E-DDY boards:
- Flash CircuitPython UF2 bootloader
- Flash firmware files
- Apply factory default configuration from YAML
- Verify board operation with telemetry check

Author: E-DDY project
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import shutil
import time
import threading
import serial
import serial.tools.list_ports
import yaml


class FlashGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("E-DDY Board Flash Tool")
        
        # Start in fullscreen/maximized mode
        self.root.state('zoomed')  # Windows maximized
        
        # State variables
        self.uf2_path = tk.StringVar()
        self.yaml_path = tk.StringVar()
        self.drive_letter = tk.StringVar(value="D:")
        self.com_port = tk.StringVar()
        self.serial_conn = None
        
        # Calibration reference values
        self.cal_vin_ref = tk.StringVar(value="12.0")
        self.cal_temp_ref = tk.StringVar(value="25.0")
        
        # Display values for monitoring
        self.display_vin_cal_a = tk.StringVar(value="--")
        self.display_vin_cal_b = tk.StringVar(value="--")
        self.display_temp_cal_a = tk.StringVar(value="--")
        self.display_temp_cal_b = tk.StringVar(value="--")
        self.display_vin_current = tk.StringVar(value="--")
        self.display_temp_current = tk.StringVar(value="--")
        
        # Build UI
        self.create_widgets()
        
        # Initial COM port scan
        self.refresh_com_ports()
    
    def create_widgets(self):
        """Build the GUI layout"""
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        row = 0
        
        # ========== File/Port Selection Section ==========
        ttk.Label(main_frame, text="Board Configuration", font=('Arial', 10, 'bold')).grid(
            row=row, column=0, columnspan=3, sticky=tk.W, pady=(0, 10))
        row += 1
        
        # RP2040 Drive Letter
        ttk.Label(main_frame, text="RP2040 Drive:").grid(row=row, column=0, sticky=tk.W, pady=5)
        drive_combo = ttk.Combobox(main_frame, textvariable=self.drive_letter, width=10)
        drive_combo['values'] = [f"{chr(d)}:" for d in range(ord('A'), ord('Z')+1)]
        drive_combo.grid(row=row, column=1, sticky=tk.W, pady=5)
        ttk.Button(main_frame, text="Refresh", command=self.refresh_drives).grid(
            row=row, column=2, sticky=tk.W, padx=5, pady=5)
        row += 1
        
        # CircuitPython UF2 File
        ttk.Label(main_frame, text="CircuitPython UF2:").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.uf2_path, width=40).grid(
            row=row, column=1, sticky=(tk.W, tk.E), pady=5)
        ttk.Button(main_frame, text="Browse", command=self.browse_uf2).grid(
            row=row, column=2, sticky=tk.W, padx=5, pady=5)
        row += 1
        
        # Default Parameters YAML File
        ttk.Label(main_frame, text="Config YAML:").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.yaml_path, width=40).grid(
            row=row, column=1, sticky=(tk.W, tk.E), pady=5)
        ttk.Button(main_frame, text="Browse", command=self.browse_yaml).grid(
            row=row, column=2, sticky=tk.W, padx=5, pady=5)
        row += 1
        
        # COM Port
        ttk.Label(main_frame, text="COM Port:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.com_combo = ttk.Combobox(main_frame, textvariable=self.com_port, width=20)
        self.com_combo.grid(row=row, column=1, sticky=tk.W, pady=5)
        ttk.Button(main_frame, text="Refresh", command=self.refresh_com_ports).grid(
            row=row, column=2, sticky=tk.W, padx=5, pady=5)
        row += 1
        
        # Separator
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=15)
        row += 1
        
        # ========== Action Buttons Section ==========
        ttk.Label(main_frame, text="Flash Operations", font=('Arial', 10, 'bold')).grid(
            row=row, column=0, columnspan=3, sticky=tk.W, pady=(0, 10))
        row += 1
        
        # Flash CircuitPython Button
        self.btn_flash_cp = ttk.Button(
            main_frame, text="1. Flash CircuitPython", command=self.flash_circuitpython, width=25)
        self.btn_flash_cp.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)
        ttk.Label(main_frame, text="Copy UF2 to RP2040 drive", foreground="gray").grid(
            row=row, column=2, sticky=tk.W, padx=5)
        row += 1
        
        # Flash Firmware Button
        self.btn_flash_fw = ttk.Button(
            main_frame, text="2. Flash Firmware", command=self.flash_firmware, width=25)
        self.btn_flash_fw.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)
        ttk.Label(main_frame, text="Copy firmware folder to drive", foreground="gray").grid(
            row=row, column=2, sticky=tk.W, padx=5)
        row += 1
        
        # Apply Config Button
        self.btn_apply_config = ttk.Button(
            main_frame, text="3. Apply Config", command=self.apply_config, width=25)
        self.btn_apply_config.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)
        ttk.Label(main_frame, text="Load YAML config to board NVM", foreground="gray").grid(
            row=row, column=2, sticky=tk.W, padx=5)
        row += 1
        
        # Check Button
        self.btn_check = ttk.Button(
            main_frame, text="4. Check Board", command=self.check_board, width=25)
        self.btn_check.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)
        ttk.Label(main_frame, text="Verify telemetry output", foreground="gray").grid(
            row=row, column=2, sticky=tk.W, padx=5)
        row += 1
        
        # Separator
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=15)
        row += 1
        
        # ========== Calibration Section ==========
        ttk.Label(main_frame, text="Calibration", font=('Arial', 10, 'bold')).grid(
            row=row, column=0, columnspan=3, sticky=tk.W, pady=(0, 10))
        row += 1
        
        # VIN Reference Value
        ttk.Label(main_frame, text="VIN Reference (V):").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.cal_vin_ref, width=15).grid(
            row=row, column=1, sticky=tk.W, pady=5)
        row += 1
        
        # Temperature Reference Value
        ttk.Label(main_frame, text="Temp Reference (°C):").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.cal_temp_ref, width=15).grid(
            row=row, column=1, sticky=tk.W, pady=5)
        row += 1
        
        # Calibrate Button
        self.btn_calibrate = ttk.Button(
            main_frame, text="5. Calibrate", command=self.calibrate_board, width=25)
        self.btn_calibrate.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)
        ttk.Label(main_frame, text="Single-point VIN & Temp cal + Save", foreground="gray").grid(
            row=row, column=2, sticky=tk.W, padx=5)
        row += 1
        
        # Read Parameters Button
        self.btn_read_params = ttk.Button(
            main_frame, text="Read Parameters", command=self.read_parameters, width=25)
        self.btn_read_params.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)
        ttk.Label(main_frame, text="Display current cal values", foreground="gray").grid(
            row=row, column=2, sticky=tk.W, padx=5)
        row += 1
        
        # Separator
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=15)
        row += 1
        
        # ========== Parameter Display Section ==========
        ttk.Label(main_frame, text="Current Parameters", font=('Arial', 10, 'bold')).grid(
            row=row, column=0, columnspan=3, sticky=tk.W, pady=(0, 10))
        row += 1
        
        # VIN Calibration Parameters
        ttk.Label(main_frame, text="VIN_CAL_A:", foreground="blue").grid(row=row, column=0, sticky=tk.W, pady=3)
        ttk.Label(main_frame, textvariable=self.display_vin_cal_a, font=('Courier', 9)).grid(
            row=row, column=1, sticky=tk.W, pady=3)
        row += 1
        
        ttk.Label(main_frame, text="VIN_CAL_B:", foreground="blue").grid(row=row, column=0, sticky=tk.W, pady=3)
        ttk.Label(main_frame, textvariable=self.display_vin_cal_b, font=('Courier', 9)).grid(
            row=row, column=1, sticky=tk.W, pady=3)
        row += 1
        
        # Temperature Calibration Parameters
        ttk.Label(main_frame, text="TEMP_CAL_A:", foreground="blue").grid(row=row, column=0, sticky=tk.W, pady=3)
        ttk.Label(main_frame, textvariable=self.display_temp_cal_a, font=('Courier', 9)).grid(
            row=row, column=1, sticky=tk.W, pady=3)
        row += 1
        
        ttk.Label(main_frame, text="TEMP_CAL_B:", foreground="blue").grid(row=row, column=0, sticky=tk.W, pady=3)
        ttk.Label(main_frame, textvariable=self.display_temp_cal_b, font=('Courier', 9)).grid(
            row=row, column=1, sticky=tk.W, pady=3)
        row += 1
        
        # Current Readings
        ttk.Label(main_frame, text="Current VIN:", foreground="green").grid(row=row, column=0, sticky=tk.W, pady=3)
        ttk.Label(main_frame, textvariable=self.display_vin_current, font=('Courier', 9, 'bold')).grid(
            row=row, column=1, sticky=tk.W, pady=3)
        row += 1
        
        ttk.Label(main_frame, text="Current Temp:", foreground="green").grid(row=row, column=0, sticky=tk.W, pady=3)
        ttk.Label(main_frame, textvariable=self.display_temp_current, font=('Courier', 9, 'bold')).grid(
            row=row, column=1, sticky=tk.W, pady=3)
        row += 1
        
        # Separator
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=15)
        row += 1
        
        # ========== Status/Log Section ==========
        ttk.Label(main_frame, text="Status Log", font=('Arial', 10, 'bold')).grid(
            row=row, column=0, columnspan=3, sticky=tk.W, pady=(0, 5))
        row += 1
        
        # Status text area
        self.status_text = scrolledtext.ScrolledText(
            main_frame, height=15, width=80, wrap=tk.WORD, state=tk.DISABLED)
        self.status_text.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        main_frame.rowconfigure(row, weight=1)
        row += 1
        
        # Clear log button
        ttk.Button(main_frame, text="Clear Log", command=self.clear_log).grid(
            row=row, column=0, sticky=tk.W, pady=5)
    
    def log(self, message, level="INFO"):
        """Append message to status log"""
        self.status_text.config(state=tk.NORMAL)
        timestamp = time.strftime("%H:%M:%S")
        self.status_text.insert(tk.END, f"[{timestamp}] {level}: {message}\n")
        self.status_text.see(tk.END)
        self.status_text.config(state=tk.DISABLED)
        self.root.update_idletasks()
    
    def clear_log(self):
        """Clear the status log"""
        self.status_text.config(state=tk.NORMAL)
        self.status_text.delete(1.0, tk.END)
        self.status_text.config(state=tk.DISABLED)
    
    def browse_uf2(self):
        """Browse for CircuitPython UF2 file"""
        filename = filedialog.askopenfilename(
            title="Select CircuitPython UF2 File",
            filetypes=[("UF2 Files", "*.uf2"), ("All Files", "*.*")]
        )
        if filename:
            self.uf2_path.set(filename)
            self.log(f"Selected UF2: {os.path.basename(filename)}")
    
    def browse_yaml(self):
        """Browse for YAML configuration file"""
        filename = filedialog.askopenfilename(
            title="Select Configuration YAML File",
            filetypes=[("YAML Files", "*.yaml *.yml"), ("All Files", "*.*")]
        )
        if filename:
            self.yaml_path.set(filename)
            self.log(f"Selected YAML: {os.path.basename(filename)}")
    
    def refresh_drives(self):
        """Refresh available drive letters"""
        self.log("Drive refresh - manually select RP2040 bootloader drive")
    
    def refresh_com_ports(self):
        """Scan and update available COM ports"""
        ports = serial.tools.list_ports.comports()
        port_list = [p.device for p in ports]
        self.com_combo['values'] = port_list
        if port_list:
            self.com_port.set(port_list[0])
            self.log(f"Found {len(port_list)} COM port(s)")
        else:
            self.log("No COM ports found", "WARNING")
    
    def read_parameters(self):
        """Read and display current calibration parameters and readings"""
        com = self.com_port.get()
        
        if not com:
            messagebox.showerror("Error", "Please select a COM port")
            return
        
        # Run in thread to avoid blocking UI
        thread = threading.Thread(target=self._read_parameters_thread, args=(com,))
        thread.daemon = True
        thread.start()
    
    def _read_parameters_thread(self, com):
        """Worker thread for reading parameters"""
        try:
            self.log(f"Reading parameters from {com}...")
            
            # Open serial connection
            ser = serial.Serial(com, baudrate=115200, timeout=2)
            time.sleep(2)
            
            # Clear buffer
            ser.reset_input_buffer()
            
            # Initialize variables
            vin_cal_a = 0.0
            vin_cal_b = 0.0
            temp_cal_a = 0.0
            temp_cal_b = 0.0
            
            # Read all parameters using GET PARAMS command
            self.log("Sending GET PARAMS command...")
            ser.write(b"GET PARAMS\n")
            time.sleep(0.2)
            
            # Read multiline response until END
            params_dict = {}
            for _ in range(50):  # Max 50 lines
                if ser.in_waiting:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    self.log(f"  RX: {line}")
                    if line == "END":
                        break
                    if "=" in line:
                        key, value = line.split("=", 1)
                        params_dict[key.strip()] = value.strip()
                time.sleep(0.05)
            
            # Extract calibration parameters
            try:
                if "VIN_CAL_A" in params_dict:
                    vin_cal_a = float(params_dict["VIN_CAL_A"])
                    self.display_vin_cal_a.set(f"{vin_cal_a:.6f}")
                else:
                    self.display_vin_cal_a.set("NOT FOUND")
                    
                if "VIN_CAL_B" in params_dict:
                    vin_cal_b = float(params_dict["VIN_CAL_B"])
                    self.display_vin_cal_b.set(f"{vin_cal_b:.6f}")
                else:
                    self.display_vin_cal_b.set("NOT FOUND")
                    
                if "TEMP_CAL_A" in params_dict:
                    temp_cal_a = float(params_dict["TEMP_CAL_A"])
                    self.display_temp_cal_a.set(f"{temp_cal_a:.6f}")
                else:
                    self.display_temp_cal_a.set("NOT FOUND")
                    
                if "TEMP_CAL_B" in params_dict:
                    temp_cal_b = float(params_dict["TEMP_CAL_B"])
                    self.display_temp_cal_b.set(f"{temp_cal_b:.6f}")
                else:
                    self.display_temp_cal_b.set("NOT FOUND")
                    
                self.log(f"Calibration params: VIN_A={vin_cal_a:.6f}, VIN_B={vin_cal_b:.6f}, TEMP_A={temp_cal_a:.6f}, TEMP_B={temp_cal_b:.6f}")
            except ValueError as e:
                self.log(f"Error parsing parameters: {e}", "ERROR")
                self.display_vin_cal_a.set("PARSE ERROR")
                self.display_vin_cal_b.set("PARSE ERROR")
                self.display_temp_cal_a.set("PARSE ERROR")
                self.display_temp_cal_b.set("PARSE ERROR")
            
            # Read current values from telemetry
            ser.write(b"SET TELEM_RATE_MS 200\n")
            time.sleep(0.1)
            ser.write(b"SET TELEM_FORMAT CSV\n")
            time.sleep(0.5)
            
            # Read a few telemetry lines and average
            vin_readings = []
            temp_readings = []
            
            for _ in range(5):
                if ser.in_waiting:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line and not line.startswith("OK") and not line.startswith("ERR"):
                        parts = line.split(',')
                        if len(parts) >= 3:
                            try:
                                vin_readings.append(float(parts[0]))
                                temp_readings.append(float(parts[2]))
                            except (ValueError, IndexError):
                                pass
                time.sleep(0.2)
            
            # Disable telemetry
            ser.write(b"SET TELEM_RATE_MS 0\n")
            time.sleep(0.1)
            
            if vin_readings and temp_readings:
                vin_avg = sum(vin_readings) / len(vin_readings)
                temp_avg = sum(temp_readings) / len(temp_readings)
                self.display_vin_current.set(f"{vin_avg:.3f} V")
                self.display_temp_current.set(f"{temp_avg:.1f} °C")
                self.log(f"Current readings: VIN={vin_avg:.3f}V, TEMP={temp_avg:.1f}°C")
            else:
                self.display_vin_current.set("No data")
                self.display_temp_current.set("No data")
                self.log("Could not read telemetry data", "WARNING")
            
            ser.close()
            self.log("Parameters read successfully", "SUCCESS")
            
        except Exception as e:
            self.log(f"Failed to read parameters: {str(e)}", "ERROR")
            import traceback
            self.log(traceback.format_exc(), "ERROR")
            self.display_vin_cal_a.set("ERROR")
            self.display_vin_cal_b.set("ERROR")
            self.display_temp_cal_a.set("ERROR")
            self.display_temp_cal_b.set("ERROR")
            self.display_vin_current.set("ERROR")
            self.display_temp_current.set("ERROR")
    
    def flash_circuitpython(self):
        """Copy UF2 file to RP2040 drive"""
        uf2 = self.uf2_path.get()
        drive = self.drive_letter.get()
        
        if not uf2:
            messagebox.showerror("Error", "Please select a CircuitPython UF2 file")
            return
        
        if not os.path.isfile(uf2):
            messagebox.showerror("Error", f"UF2 file not found: {uf2}")
            return
        
        if not os.path.isdir(drive + "\\"):
            messagebox.showerror("Error", f"Drive {drive} not accessible.\n\nMake sure the RP2040 is in bootloader mode (RPI-RP2 drive visible)")
            return
        
        try:
            self.log(f"Flashing CircuitPython to {drive}...")
            dest_path = os.path.join(drive + "\\", os.path.basename(uf2))
            shutil.copy2(uf2, dest_path)
            self.log(f"Copied {os.path.basename(uf2)} to {drive}", "SUCCESS")
            self.log("Board will reboot automatically. Wait for CIRCUITPY drive to appear before flashing firmware.")
        except Exception as e:
            self.log(f"Flash failed: {str(e)}", "ERROR")
            messagebox.showerror("Flash Error", f"Failed to flash CircuitPython:\n\n{str(e)}")
    
    def flash_firmware(self):
        """Copy firmware folder to CircuitPython drive"""
        drive = self.drive_letter.get()
        
        # Get firmware folder path (relative to this script)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        firmware_src = os.path.join(os.path.dirname(script_dir), "firmware")
        
        if not os.path.isdir(firmware_src):
            messagebox.showerror("Error", f"Firmware folder not found: {firmware_src}")
            return
        
        if not os.path.isdir(drive + "\\"):
            messagebox.showerror("Error", f"Drive {drive} not accessible.\n\nMake sure CIRCUITPY drive is mounted.")
            return
        
        try:
            self.log(f"Flashing firmware to {drive}...")
            
            # Copy each file from firmware folder to drive root
            files_copied = 0
            for filename in os.listdir(firmware_src):
                src_file = os.path.join(firmware_src, filename)
                if os.path.isfile(src_file):
                    dest_file = os.path.join(drive + "\\", filename)
                    shutil.copy2(src_file, dest_file)
                    self.log(f"  Copied: {filename}")
                    files_copied += 1
            
            self.log(f"Firmware flash complete: {files_copied} file(s) copied", "SUCCESS")
            self.log("Board will reboot. Wait a few seconds before applying config.")
        except Exception as e:
            self.log(f"Firmware flash failed: {str(e)}", "ERROR")
            messagebox.showerror("Flash Error", f"Failed to flash firmware:\n\n{str(e)}")
    
    def apply_config(self):
        """Apply YAML configuration to board via serial"""
        yaml_file = self.yaml_path.get()
        com = self.com_port.get()
        
        if not yaml_file:
            messagebox.showerror("Error", "Please select a configuration YAML file")
            return
        
        if not os.path.isfile(yaml_file):
            messagebox.showerror("Error", f"YAML file not found: {yaml_file}")
            return
        
        if not com:
            messagebox.showerror("Error", "Please select a COM port")
            return
        
        # Run in thread to avoid blocking UI
        thread = threading.Thread(target=self._apply_config_thread, args=(yaml_file, com))
        thread.daemon = True
        thread.start()
    
    def _apply_config_thread(self, yaml_file, com):
        """Worker thread for applying configuration"""
        try:
            self.log(f"Loading config from {os.path.basename(yaml_file)}...")
            
            # Load YAML
            with open(yaml_file, 'r') as f:
                config = yaml.safe_load(f)
            
            self.log(f"Connecting to {com}...")
            
            # Open serial connection
            ser = serial.Serial(com, baudrate=115200, timeout=2)
            time.sleep(2)  # Wait for board to be ready
            
            # Clear any pending data
            ser.reset_input_buffer()
            
            self.log("Connected. Applying parameters...")
            
            # Apply parameters
            params_applied = 0
            if 'parameters' in config:
                for key, value in config['parameters'].items():
                    cmd = f"SET {key} {value}\n"
                    ser.write(cmd.encode('utf-8'))
                    time.sleep(0.05)  # Small delay between commands
                    response = ser.readline().decode('utf-8', errors='ignore').strip()
                    if response:
                        self.log(f"  {key} = {value} -> {response}")
                    params_applied += 1
            
            self.log(f"Applied {params_applied} parameters")
            
            # Apply LUTs if present
            if 'lut_adc_to_temp' in config:
                self.log("Applying ADC_TO_TEMP LUT...")
                lut_data = config['lut_adc_to_temp']
                lut_str = ' '.join([f"{adc},{temp}" for adc, temp in lut_data])
                cmd = f"SET LUT ADC_TO_TEMP {lut_str}\n"
                ser.write(cmd.encode('utf-8'))
                time.sleep(0.1)
                response = ser.readline().decode('utf-8', errors='ignore').strip()
                self.log(f"  ADC_TO_TEMP -> {response}")
            
            if 'lut_temp_to_duty' in config:
                self.log("Applying TEMP_TO_DUTY LUT...")
                lut_data = config['lut_temp_to_duty']
                lut_str = ' '.join([f"{temp},{duty}" for temp, duty in lut_data])
                cmd = f"SET LUT TEMP_TO_DUTY {lut_str}\n"
                ser.write(cmd.encode('utf-8'))
                time.sleep(0.1)
                response = ser.readline().decode('utf-8', errors='ignore').strip()
                self.log(f"  TEMP_TO_DUTY -> {response}")
            
            # Save to NVM
            self.log("Saving to NVM...")
            ser.write(b"SAVE\n")
            time.sleep(0.2)
            response = ser.readline().decode('utf-8', errors='ignore').strip()
            self.log(f"  SAVE -> {response}")
            
            ser.close()
            self.log("Configuration applied successfully!", "SUCCESS")
            
        except Exception as e:
            self.log(f"Config apply failed: {str(e)}", "ERROR")
            messagebox.showerror("Apply Error", f"Failed to apply configuration:\n\n{str(e)}")
    
    def check_board(self):
        """Read and display telemetry from board"""
        com = self.com_port.get()
        
        if not com:
            messagebox.showerror("Error", "Please select a COM port")
            return
        
        # Run in thread to avoid blocking UI
        thread = threading.Thread(target=self._check_board_thread, args=(com,))
        thread.daemon = True
        thread.start()
    
    def _check_board_thread(self, com):
        """Worker thread for checking board telemetry"""
        try:
            self.log(f"Connecting to {com} for telemetry check...")
            
            # Open serial connection
            ser = serial.Serial(com, baudrate=115200, timeout=2)
            time.sleep(2)
            
            # Clear buffer
            ser.reset_input_buffer()
            
            # Enable telemetry
            self.log("Enabling telemetry (CSV mode, 500ms rate)...")
            ser.write(b"SET TELEM_RATE_MS 500\n")
            time.sleep(0.1)
            ser.write(b"SET TELEM_FORMAT CSV\n")
            time.sleep(0.5)
            
            # Read telemetry for 5 seconds
            self.log("Reading telemetry for 5 seconds...")
            self.log("-" * 60)
            
            start_time = time.time()
            lines_read = 0
            while (time.time() - start_time) < 5.0:
                if ser.in_waiting:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line and not line.startswith("OK") and not line.startswith("ERR"):
                        self.log(f"  {line}")
                        lines_read += 1
            
            self.log("-" * 60)
            
            # Disable telemetry
            ser.write(b"SET TELEM_RATE_MS 0\n")
            time.sleep(0.1)
            
            ser.close()
            
            if lines_read > 0:
                self.log(f"Board check complete: {lines_read} telemetry lines received", "SUCCESS")
            else:
                self.log("No telemetry received - check board connection", "WARNING")
                messagebox.showwarning("Check Complete", "No telemetry received.\n\nBoard may not be running or COM port is incorrect.")
            
        except Exception as e:
            self.log(f"Board check failed: {str(e)}", "ERROR")
            messagebox.showerror("Check Error", f"Failed to check board:\n\n{str(e)}")
    
    def calibrate_board(self):
        """Perform single-point calibration for VIN and Temperature"""
        com = self.com_port.get()
        
        if not com:
            messagebox.showerror("Error", "Please select a COM port")
            return
        
        try:
            vin_ref = float(self.cal_vin_ref.get())
            temp_ref = float(self.cal_temp_ref.get())
        except ValueError:
            messagebox.showerror("Error", "Invalid reference values. Please enter valid numbers.")
            return
        
        # Run in thread to avoid blocking UI
        thread = threading.Thread(target=self._calibrate_board_thread, args=(com, vin_ref, temp_ref))
        thread.daemon = True
        thread.start()
    
    def _calibrate_board_thread(self, com, vin_ref, temp_ref):
        """Worker thread for calibration - adjusts offset to match reference values"""
        try:
            self.log(f"Starting offset calibration: VIN={vin_ref}V, Temp={temp_ref}°C...")
            self.log(f"Connecting to {com}...")
            
            # Open serial connection
            ser = serial.Serial(com, baudrate=115200, timeout=2)
            time.sleep(2)
            
            # Clear buffer
            ser.reset_input_buffer()
            
            # Step 1: Get current calibration parameters using GET PARAMS
            self.log("Reading current calibration parameters...")
            ser.write(b"GET PARAMS\n")
            time.sleep(0.2)
            
            # Read multiline response until END
            params_dict = {}
            for _ in range(50):
                if ser.in_waiting:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line == "END":
                        break
                    if "=" in line:
                        key, value = line.split("=", 1)
                        params_dict[key.strip()] = value.strip()
                time.sleep(0.05)
            
            # Extract calibration parameters
            try:
                vin_cal_a = float(params_dict.get("VIN_CAL_A", "1.0"))
                vin_cal_b = float(params_dict.get("VIN_CAL_B", "0.0"))
                temp_cal_a = float(params_dict.get("TEMP_CAL_A", "1.0"))
                temp_cal_b = float(params_dict.get("TEMP_CAL_B", "0.0"))
            except (ValueError, KeyError) as e:
                ser.close()
                raise Exception(f"Failed to parse calibration parameters: {e}")
            
            self.log(f"Current cal: VIN_A={vin_cal_a}, VIN_B={vin_cal_b:.3f}, TEMP_A={temp_cal_a}, TEMP_B={temp_cal_b:.3f}")
            
            # Step 2: Read current calibrated values from telemetry
            self.log("Reading current calibrated values (5 second average)...")
            ser.write(b"SET TELEM_RATE_MS 100\n")
            time.sleep(0.1)
            ser.write(b"SET TELEM_FORMAT CSV\n")
            time.sleep(0.5)
            
            # Read telemetry for 5 seconds and average
            vin_readings = []
            temp_readings = []
            
            start_time = time.time()
            while (time.time() - start_time) < 5.0:
                if ser.in_waiting:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line and not line.startswith("OK") and not line.startswith("ERR"):
                        parts = line.split(',')
                        if len(parts) >= 3:
                            try:
                                vin_readings.append(float(parts[0]))
                                temp_readings.append(float(parts[2]))  # temp_c is 3rd field
                            except (ValueError, IndexError):
                                pass
                time.sleep(0.05)
            
            # Disable telemetry
            ser.write(b"SET TELEM_RATE_MS 0\n")
            time.sleep(0.1)
            
            if not vin_readings or not temp_readings:
                ser.close()
                raise Exception("Failed to read telemetry data")
            
            # Average readings
            vin_measured = sum(vin_readings) / len(vin_readings)
            temp_measured = sum(temp_readings) / len(temp_readings)
            
            self.log(f"Measured (with current cal, {len(vin_readings)} samples): VIN={vin_measured:.3f}V, Temp={temp_measured:.1f}°C")
            
            # Step 3: Calculate offset adjustment needed
            # Current: output = A * input + B
            # We want to adjust B so that output matches reference
            # Since output = A * input + B, and we want new_output = reference
            # new_B = B + (reference - current_output)
            vin_offset = vin_ref - vin_measured
            temp_offset = temp_ref - temp_measured
            
            self.log(f"Calculated offsets: VIN={vin_offset:+.3f}V, TEMP={temp_offset:+.1f}°C")
            
            # Apply offset adjustment (keep A unchanged, adjust B)
            new_vin_cal_b = vin_cal_b + vin_offset
            new_temp_cal_b = temp_cal_b + temp_offset
            
            self.log(f"New calibration:")
            self.log(f"  VIN_CAL_A={vin_cal_a} (unchanged), VIN_CAL_B={vin_cal_b:.6f} → {new_vin_cal_b:.6f}")
            self.log(f"  TEMP_CAL_A={temp_cal_a} (unchanged), TEMP_CAL_B={temp_cal_b:.6f} → {new_temp_cal_b:.6f}")
            
            # Step 4: Apply new calibration
            self.log("Applying adjusted calibration...")
            cmd = f"SET VIN_CAL_B {new_vin_cal_b:.6f}\n"
            ser.write(cmd.encode('utf-8'))
            time.sleep(0.1)
            response = ser.readline().decode('utf-8', errors='ignore').strip()
            self.log(f"  VIN_CAL_B -> {response}")
            
            cmd = f"SET TEMP_CAL_B {new_temp_cal_b:.6f}\n"
            ser.write(cmd.encode('utf-8'))
            time.sleep(0.1)
            response = ser.readline().decode('utf-8', errors='ignore').strip()
            self.log(f"  TEMP_CAL_B -> {response}")
            
            # Step 5: Save to NVM
            self.log("Saving calibration to NVM...")
            ser.write(b"SAVE\n")
            time.sleep(0.2)
            response = ser.readline().decode('utf-8', errors='ignore').strip()
            self.log(f"  SAVE -> {response}")
            
            # Step 6: Verify calibration by reading telemetry again
            self.log("Verifying calibration (5 second average)...")
            ser.write(b"SET TELEM_RATE_MS 100\n")
            time.sleep(0.1)
            ser.write(b"SET TELEM_FORMAT CSV\n")
            time.sleep(0.5)
            
            # Read telemetry for 5 seconds and average
            vin_verify = []
            temp_verify = []
            
            start_time = time.time()
            while (time.time() - start_time) < 5.0:
                if ser.in_waiting:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line and not line.startswith("OK") and not line.startswith("ERR"):
                        parts = line.split(',')
                        if len(parts) >= 3:
                            try:
                                vin_verify.append(float(parts[0]))
                                temp_verify.append(float(parts[2]))
                            except (ValueError, IndexError):
                                pass
                time.sleep(0.05)
            
            # Disable telemetry
            ser.write(b"SET TELEM_RATE_MS 0\n")
            time.sleep(0.1)
            
            ser.close()
            
            # Calculate verification results
            if vin_verify and temp_verify:
                vin_final = sum(vin_verify) / len(vin_verify)
                temp_final = sum(temp_verify) / len(temp_verify)
                
                vin_error_pct = ((vin_final - vin_ref) / vin_ref) * 100.0 if vin_ref != 0 else 0
                temp_error_pct = ((temp_final - temp_ref) / temp_ref) * 100.0 if temp_ref != 0 else 0
                
                self.log(f"Verification ({len(vin_verify)} samples): VIN={vin_final:.3f}V (error: {vin_error_pct:+.2f}%), TEMP={temp_final:.1f}°C (error: {temp_error_pct:+.2f}%)")
                
                self.log("Offset calibration complete and saved!", "SUCCESS")
                self.log(f"Before: VIN={vin_measured:.3f}V, Temp={temp_measured:.1f}°C", "SUCCESS")
                self.log(f"After: VIN={vin_final:.3f}V (error: {vin_error_pct:+.2f}%), Temp={temp_final:.1f}°C (error: {temp_error_pct:+.2f}%)", "SUCCESS")
            else:
                self.log("Offset calibration complete and saved!", "SUCCESS")
                self.log(f"VIN: {vin_measured:.3f}V → {vin_ref}V (offset {vin_offset:+.3f}V)", "SUCCESS")
                self.log(f"Temp: {temp_measured:.1f}°C → {temp_ref}°C (offset {temp_offset:+.1f}°C)", "SUCCESS")
                self.log("Warning: Could not verify calibration.", "WARNING")
            
        except Exception as e:
            self.log(f"Calibration failed: {str(e)}", "ERROR")
            messagebox.showerror("Calibration Error", f"Failed to calibrate board:\n\n{str(e)}")


def main():
    root = tk.Tk()
    app = FlashGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
