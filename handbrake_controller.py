import serial
import time
import vgamepad as vg
import tkinter as tk
from tkinter import ttk
import json
from serial.tools import list_ports

class HandbrakeController:
    def __init__(self):
        try:
            self.gamepad = vg.VX360Gamepad()
            print("Virtual controller created")
            self.gamepad.reset()
            self.gamepad.update()
        except Exception as e:
            print(f"Error initializing gamepad: {e}")
            self.gamepad = None

        self.serial = None
        
        # Settings
        self.settings = {
            'threshold': 50,  # Default 50% threshold
            'digital_mode': True,  # True for on/off, False for analog
            'last_port': 'COM1'
        }
        self.load_settings()

    def connect(self, port):
        try:
            if self.serial:
                self.serial.close()
            self.serial = serial.Serial(port, 115200, timeout=1)
            self.settings['last_port'] = port
            self.save_settings()
            print(f"Connected to {port}")
            return True
        except Exception as e:
            print(f"Connection error: {e}")
            return False

    def update_handbrake(self):
        if not self.serial or not self.gamepad:
            return False

        try:
            if self.serial.in_waiting:
                raw_data = self.serial.readline().decode().strip()
                if raw_data:
                    handbrake_raw = int(raw_data)
                    handbrake_percent = handbrake_raw / 1023.0 * 100

                    if self.settings['digital_mode']:
                        # Digital mode (button press)
                        if handbrake_percent > self.settings['threshold']:
                            self.gamepad.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
                        else:
                            self.gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
                    else:
                        # Analog mode (trigger)
                        self.gamepad.right_trigger(value=int(handbrake_percent * 327.67))

                    self.gamepad.update()
                    return handbrake_percent
        except Exception as e:
            print(f"Update error: {e}")
        return False

    def load_settings(self):
        try:
            with open('handbrake_settings.json', 'r') as f:
                saved_settings = json.load(f)
                self.settings.update(saved_settings)
        except:
            print("No settings file found, using defaults")

    def save_settings(self):
        with open('handbrake_settings.json', 'w') as f:
            json.dump(self.settings, f)

class HandbrakeGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Handbrake Controller")
        self.root.geometry("300x400")
        
        # Set running flag before creating widgets
        self.running = True
        
        self.controller = HandbrakeController()
        self.create_widgets()

    def create_widgets(self):
        # COM Port Selection
        port_frame = ttk.LabelFrame(self.root, text="Connection", padding=10)
        port_frame.pack(fill='x', padx=5, pady=5)

        self.ports = [p.device for p in list_ports.comports()]
        self.port_var = tk.StringVar(value=self.controller.settings['last_port'])
        
        ttk.Label(port_frame, text="COM Port:").pack(side='left', padx=5)
        self.port_combo = ttk.Combobox(port_frame, textvariable=self.port_var, values=self.ports)
        self.port_combo.pack(side='left', padx=5)
        
        ttk.Button(port_frame, text="Connect", command=self.connect).pack(side='left', padx=5)
        ttk.Button(port_frame, text="Refresh", command=self.refresh_ports).pack(side='left', padx=5)

        # Add a status label
        self.status_label = ttk.Label(port_frame, text="Not Connected", foreground="red")
        self.status_label.pack(side='left', padx=5)

        # Mode Selection
        mode_frame = ttk.LabelFrame(self.root, text="Mode", padding=10)
        mode_frame.pack(fill='x', padx=5, pady=5)

        self.mode_var = tk.BooleanVar(value=self.controller.settings['digital_mode'])
        ttk.Radiobutton(mode_frame, text="Digital (Button)", variable=self.mode_var, 
                       value=True, command=self.update_mode).pack(side='left', padx=5)
        ttk.Radiobutton(mode_frame, text="Analog (Axis)", variable=self.mode_var, 
                       value=False, command=self.update_mode).pack(side='left', padx=5)

        # Threshold Setting
        threshold_frame = ttk.LabelFrame(self.root, text="Digital Threshold", padding=10)
        threshold_frame.pack(fill='x', padx=5, pady=5)

        self.threshold_var = tk.IntVar(value=self.controller.settings['threshold'])
        threshold_scale = ttk.Scale(threshold_frame, from_=1, to=100, 
                                  variable=self.threshold_var, orient='horizontal',
                                  command=self.update_threshold)
        threshold_scale.pack(fill='x', padx=5)
        
        # Value Display
        self.value_frame = ttk.LabelFrame(self.root, text="Current Value", padding=10)
        self.value_frame.pack(fill='x', padx=5, pady=5)
        
        self.value_bar = ttk.Progressbar(self.value_frame, length=200, mode='determinate')
        self.value_bar.pack(fill='x', padx=5, pady=5)
        
        self.value_label = ttk.Label(self.value_frame, text="0%")
        self.value_label.pack()

        # Start the display update
        self.root.after(10, self.update_display)

    def connect(self):
        if self.controller.connect(self.port_var.get()):
            self.status_label.config(text="Connected", foreground="green")
        else:
            self.status_label.config(text="Connection Failed", foreground="red")

    def refresh_ports(self):
        self.ports = [p.device for p in list_ports.comports()]
        self.port_combo['values'] = self.ports

    def update_mode(self):
        self.controller.settings['digital_mode'] = self.mode_var.get()
        self.controller.save_settings()

    def update_threshold(self, *args):
        self.controller.settings['threshold'] = self.threshold_var.get()
        self.controller.save_settings()

    def update_display(self):
        if self.running:
            value = self.controller.update_handbrake()
            if value is not False:
                self.value_bar['value'] = value
                self.value_label['text'] = f"{value:.1f}%"
            self.root.after(10, self.update_display)

    def run(self):
        try:
            self.root.mainloop()
        finally:
            self.running = False
            if self.controller.serial:
                self.controller.serial.close()

if __name__ == "__main__":
    app = HandbrakeGUI()
    app.run() 