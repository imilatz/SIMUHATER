import serial
import time
import vgamepad as vg
from enum import Enum, auto
import tkinter as tk
from tkinter import ttk, simpledialog
import pystray
from PIL import Image, ImageTk
import threading
import queue
import pyvjoy  # Changed from vjoy to pyvjoy
import json
import os
import math
import inspect
import ctypes
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import serial.tools.list_ports
import darkdetect

class ControlProfile(Enum):
    MSFS = "Microsoft Flight Simulator"
    DCS = "DCS World"
    XPLANE = "X-Plane"
    IL2 = "IL-2 Sturmovik"
    WAR_THUNDER = "War Thunder"

class ControllerType(Enum):
    XBOX = "Xbox Controller"
    VJOY = "vJoy Device"

class ControlPanelConfig:
    def __init__(self):
        # Control types
        self.CONTROL_TYPES = ["Axis", "Switch", "Button", "Disabled"] 
        
        # Default configuration for each pot
        self.pot_config = []
        
        # Initialize 7 pots with default settings
        for i in range(7):
            self.pot_config.append({
                'name': f"Pot {i+1}",
                'type': "Axis",  # Axis, Switch, Button, or Disabled
                'invert': False,
                'min': 0,
                'max': 100,
                'threshold': 50,  # For switch/button mode
                'vjoy_axis': None,  # For mapping to vJoy
                'button_id': None,  # For mapping to button
                'calibrated_min': 0,
                'calibrated_max': 100
            })
    
    def get_pot_names(self):
        """Return list of pot names"""
        return [pot['name'] for pot in self.pot_config]
    
    def set_pot_name(self, index, name):
        """Set name for a pot"""
        if 0 <= index < len(self.pot_config):
            self.pot_config[index]['name'] = name
    
    def set_pot_type(self, index, type_name):
        """Set type for a pot"""
        if 0 <= index < len(self.pot_config) and type_name in self.CONTROL_TYPES:
            self.pot_config[index]['type'] = type_name
    
    def set_pot_threshold(self, index, threshold):
        """Set threshold for a pot in switch/button mode"""
        if 0 <= index < len(self.pot_config):
            self.pot_config[index]['threshold'] = threshold
    
    def toggle_pot_inversion(self, index):
        """Toggle inversion for a pot"""
        if 0 <= index < len(self.pot_config):
            self.pot_config[index]['invert'] = not self.pot_config[index]['invert']
    
    def calibrate_pot_min(self, index, value):
        """Set calibrated minimum for a pot"""
        if 0 <= index < len(self.pot_config):
            self.pot_config[index]['calibrated_min'] = value
    
    def calibrate_pot_max(self, index, value):
        """Set calibrated maximum for a pot"""
        if 0 <= index < len(self.pot_config):
            self.pot_config[index]['calibrated_max'] = value
    
    def process_pot_value(self, index, raw_value):
        """Process a pot value based on its configuration"""
        if index < 0 or index >= len(self.pot_config):
            return 0
        
        config = self.pot_config[index]
        
        # Skip disabled controls
        if config['type'] == "Disabled":
            return 0
        
        # Ensure raw_value is within expected range
        raw_value = max(0, min(1023, raw_value))
        
        # Apply calibration
        cal_min = config['calibrated_min']
        cal_max = config['calibrated_max']
        
        # Ensure calibration values are valid
        if cal_min >= cal_max:
            # Default to full range if calibration is invalid
            cal_min = 0
            cal_max = 1023
        
        # Map from calibrated min to max
        if cal_max == cal_min:  # Avoid division by zero
            calibrated = 50
        else:
            # Map from calibrated min to max
            calibrated = (raw_value - cal_min) / (cal_max - cal_min) * 100
            calibrated = max(0, min(100, calibrated))
        
        # Apply inversion if needed
        if config['invert']:
            calibrated = 100 - calibrated
        
        # Process based on type
        if config['type'] == "Axis":
            return calibrated
        elif config['type'] == "Switch" or config['type'] == "Button":
            return 100 if calibrated > config['threshold'] else 0
        
        return calibrated

class FlightControls:
    def __init__(self):
        # Controller type selection
        self.controller_type = ControllerType.XBOX
        
        # Initialize both controller types
        self.gamepad = vg.VX360Gamepad()  # Main gamepad for all games
        self.current_profile = ControlProfile.MSFS
        
        # Initialize vJoy with better error checking
        try:
            self.vjoy_dev = pyvjoy.VJoyDevice(1)  # Use device ID 1
            
            # Test if we can actually write to the axes
            self.vjoy_dev.data.wAxisX = 16384  # Forward thrust
            self.vjoy_dev.data.wAxisY = 16384  # Prop
            self.vjoy_dev.data.wAxisZ = 16384  # Mixture
            self.vjoy_dev.data.wAxisXRot = 0   # Reverse thrust
            self.vjoy_dev.update()
            
            print("vJoy initialized successfully")
            print(f"X Axis (Forward Thrust): {self.vjoy_dev.data.wAxisX}")
            print(f"Y Axis (Prop): {self.vjoy_dev.data.wAxisY}")
            print(f"Z Axis (Mixture): {self.vjoy_dev.data.wAxisZ}")
            print(f"XRot Axis (Reverse Thrust): {self.vjoy_dev.data.wAxisXRot}")
            
        except Exception as e:
            print(f"vJoy error: {str(e)}")
            self.vjoy_dev = None
            
        # Calibration values for each control
        self.calibration = {
            'throttle': {'min': 0, 'max': 100, 'idle': 0},  # Forward thrust (idle to max)
            'reverse': {'min': 0, 'max': 100, 'idle': 0},   # Reverse thrust (idle to max)
            'prop': {'min': 0, 'max': 100, 'idle': 0},      # Changed to use idle point like throttle
            'mixture': {'min': 0, 'max': 100, 'idle': 0}    # Changed to use idle point like throttle
        }
        
        # Axis inversion settings
        self.invert_axis = {
            'throttle': False,
            'reverse': False,
            'prop': False,
            'mixture': False
        }
        
        # Function mode for prop control
        self.prop_as_speedbrake = False
        
        # Add control panel configuration
        self.control_panel = ControlPanelConfig()
        
        # Initialize button states
        self.button_states = {}
        self.last_pot_values = {}

    def calibrate_simple(self, value, control_type):
        """Simple calibration for prop and mixture"""
        cal = self.calibration[control_type]
        
        # Ensure value is a float for calculations
        value = float(value)
        
        # If value is below idle point, it's at minimum
        if value <= cal['idle']:
            return 0.0
        
        # Map from idle to max
        if cal['max'] == cal['idle']:  # Avoid division by zero
            return 100.0
            
        ratio = (value - cal['idle']) / (cal['max'] - cal['idle'])
        ratio = max(0.0, min(1.0, ratio))  # Clamp between 0 and 1
        return ratio * 100.0  # Map to 0 to 100

    def calibrate_value(self, value, control_type):
        """Apply calibration to a raw value"""
        cal = self.calibration[control_type]
        
        # Ensure value is a float for calculations
        value = float(value)
        
        # Map the value from the input range to the output range
        if value <= cal['center']:
            # Map from min to center
            if cal['center'] == cal['min']:  # Avoid division by zero
                return 0.0
            ratio = (value - cal['min']) / (cal['center'] - cal['min'])
            return ratio * 50.0  # Map to 0 to 50
        else:
            # Map from center to max
            if cal['max'] == cal['center']:  # Avoid division by zero
                return 100.0
            ratio = (value - cal['center']) / (cal['max'] - cal['center'])
            return 50.0 + ratio * 50.0  # Map to 50 to 100

    def calibrate_throttle(self, value):
        """Apply calibration to throttle value"""
        cal = self.calibration['throttle']
        
        # Ensure value is a float for calculations
        value = float(value)
        
        # If value is below idle point, it's in reverse territory
        if value <= cal['idle']:
            return 0.0  # No forward thrust
        
        # Map from idle to max
        if cal['max'] == cal['idle']:  # Avoid division by zero
            return 100.0
            
        ratio = (value - cal['idle']) / (cal['max'] - cal['idle'])
        ratio = max(0.0, min(1.0, ratio))  # Clamp between 0 and 1
        return ratio * 100.0  # Map to 0 to 100
    
    def calibrate_reverse(self, value):
        """Apply calibration to reverse value"""
        cal = self.calibration['reverse']
        
        # Ensure value is a float for calculations
        value = float(value)
        
        # If value is above idle point, it's in forward territory
        if value >= cal['idle']:
            return 0.0  # No reverse thrust
        
        # Map from min to idle
        if cal['idle'] == cal['min']:  # Avoid division by zero
            return 100.0
            
        ratio = (cal['idle'] - value) / (cal['idle'] - cal['min'])
        ratio = max(0.0, min(1.0, ratio))  # Clamp between 0 and 1
        return ratio * 100.0  # Map to 0 to 100

    def process_throttle_input(self, raw_value):
        """Process throttle input to determine forward and reverse values"""
        # Calculate forward and reverse thrust
        forward = self.calibrate_throttle(raw_value)
        reverse = self.calibrate_reverse(raw_value)
        
        # Apply inversion if needed
        forward = self.apply_inversion(forward, 'throttle')
        reverse = self.apply_inversion(reverse, 'reverse')
            
        return forward, reverse

    def apply_inversion(self, value, control_type):
        """Apply axis inversion if enabled"""
        if self.invert_axis[control_type]:
            return 100 - value
        return value

    def map_controls_msfs(self, throttle, prop, mixture):
        # MSFS mapping
        if throttle >= 0:
            self.gamepad.right_trigger(value=int(throttle * 327.67))
            self.gamepad.left_trigger(value=0)
        else:
            self.gamepad.right_trigger(value=0)
            self.gamepad.left_trigger(value=int(abs(throttle) * 327.67))
            
        self.gamepad.right_joystick(x_value=0, y_value=int(prop * 655.34 - 32768))
        self.gamepad.left_joystick(x_value=0, y_value=int(mixture * 655.34 - 32768))
    
    def map_controls_dcs(self, throttle, prop, mixture):
        # DCS mapping - all on one stick
        self.gamepad.left_joystick(
            x_value=int(prop * 655.34 - 32768),
            y_value=int(throttle * 655.34 - 32768)
        )
        self.gamepad.right_joystick(
            x_value=0,
            y_value=int(mixture * 655.34 - 32768)
        )
    
    def map_controls_xplane(self, throttle, prop, mixture):
        # X-Plane mapping
        if throttle >= 0:
            self.gamepad.right_trigger(value=int(throttle * 327.67))
        else:
            self.gamepad.left_trigger(value=int(abs(throttle) * 327.67))
            
        # Combine prop and mixture on right stick
        self.gamepad.right_joystick(
            x_value=int(mixture * 655.34 - 32768),
            y_value=int(prop * 655.34 - 32768)
        )
    
    def map_controls_il2(self, throttle, prop, mixture):
        # IL-2 mapping
        self.gamepad.left_trigger(value=int((mixture + 100) * 163.835))
        self.gamepad.right_trigger(value=int((prop + 100) * 163.835))
        self.gamepad.left_joystick(y_value=int(throttle * 655.34 - 32768))

    def map_controls_war_thunder(self, throttle_raw, prop_raw, mixture_raw):
        if self.vjoy_dev is None:
            return 0, 0, 0, 0
            
        try:
            # Process throttle to get forward and reverse values
            forward_throttle, reverse_throttle = self.process_throttle_input(throttle_raw)
            
            # Process prop and mixture
            if self.prop_as_speedbrake:
                # When prop is used as speedbrake, we want 0 at idle and 100 at max deflection
                prop = self.calibrate_simple(prop_raw, 'prop')
                prop = self.apply_inversion(prop, 'prop')
            else:
                # Normal prop control
                prop = self.calibrate_simple(prop_raw, 'prop')
                prop = self.apply_inversion(prop, 'prop')
                
            mixture = self.calibrate_simple(mixture_raw, 'mixture')
            mixture = self.apply_inversion(mixture, 'mixture')
            
            # Map forward throttle to X axis (0-32768)
            forward_value = int(forward_throttle * 327.68)  # 0-100 to 0-32768
            forward_value = max(0, min(32768, forward_value))
            self.vjoy_dev.data.wAxisX = forward_value
            
            # Map reverse throttle to XRot axis (0-32768)
            reverse_value = int(reverse_throttle * 327.68)  # 0-100 to 0-32768
            reverse_value = max(0, min(32768, reverse_value))
            self.vjoy_dev.data.wAxisXRot = reverse_value
            
            # Map prop to Y axis (0-32768)
            prop_value = int(prop * 327.68)  # 0,100 to 0,32768
            prop_value = max(0, min(32768, prop_value))
            self.vjoy_dev.data.wAxisY = prop_value
            
            # Map mixture to Z axis (0-32768)
            mixture_value = int(mixture * 327.68)  # 0,100 to 0,32768
            mixture_value = max(0, min(32768, mixture_value))
            self.vjoy_dev.data.wAxisZ = mixture_value
            
            # Update all axes at once
            self.vjoy_dev.update()
            
            # Print debug values occasionally
            if forward_value % 1000 == 0 or reverse_value % 1000 == 0:
                print(f"vJoy values - Forward: {forward_value}, Reverse: {reverse_value}, Prop/Speedbrake: {prop_value}, Mix: {mixture_value}")
                
            return forward_throttle, reverse_throttle, prop, mixture
                
        except Exception as e:
            print(f"vJoy update error: {str(e)}")
            return 0, 0, 0, 0

    def apply_mapping(self, throttle_raw, prop_raw, mixture_raw):
        # Apply calibration to prop and mixture using the simpler method
        prop = self.calibrate_simple(prop_raw, 'prop')
        mixture = self.calibrate_simple(mixture_raw, 'mixture')
        
        # Apply axis inversion to prop and mixture
        prop = self.apply_inversion(prop, 'prop')
        mixture = self.apply_inversion(mixture, 'mixture')
        
        # For War Thunder or when vJoy is selected, use vJoy mapping
        if self.controller_type == ControllerType.VJOY or self.current_profile == ControlProfile.WAR_THUNDER:
            return self.map_controls_vjoy(throttle_raw, prop_raw, mixture_raw)
        else:
            # For other profiles with Xbox controller, use the appropriate mapping
            mapping_functions = {
                ControlProfile.MSFS: self.map_controls_msfs,
                ControlProfile.DCS: self.map_controls_dcs,
                ControlProfile.XPLANE: self.map_controls_xplane,
                ControlProfile.IL2: self.map_controls_il2
            }
            
            # Process throttle here for Xbox controller
            forward, reverse = self.process_throttle_input(throttle_raw)
            mapping_functions[self.current_profile](forward - reverse, prop, mixture)
            return forward, reverse, prop, mixture
    
    def next_profile(self):
        profiles = list(ControlProfile)
        current_index = profiles.index(self.current_profile)
        self.current_profile = profiles[(current_index + 1) % len(profiles)]
        return self.current_profile

    def map_controls_vjoy(self, throttle_raw, prop_raw, mixture_raw):
        """Map controls to vJoy device regardless of profile"""
        if self.vjoy_dev is None:
            return 0, 0, 0, 0
            
        try:
            # Process throttle to get forward and reverse values
            forward_throttle, reverse_throttle = self.process_throttle_input(throttle_raw)
            
            # Process prop and mixture
            if self.prop_as_speedbrake:
                # When prop is used as speedbrake, we want 0 at idle and 100 at max deflection
                prop = self.calibrate_simple(prop_raw, 'prop')
                prop = self.apply_inversion(prop, 'prop')
            else:
                # Normal prop control
                prop = self.calibrate_simple(prop_raw, 'prop')
                prop = self.apply_inversion(prop, 'prop')
                
            mixture = self.calibrate_simple(mixture_raw, 'mixture')
            mixture = self.apply_inversion(mixture, 'mixture')
            
            # Map forward throttle to X axis (0-32768)
            forward_value = int(forward_throttle * 327.68)  # 0-100 to 0-32768
            forward_value = max(0, min(32768, forward_value))
            self.vjoy_dev.data.wAxisX = forward_value
            
            # Map reverse throttle to XRot axis (0-32768)
            reverse_value = int(reverse_throttle * 327.68)  # 0-100 to 0-32768
            reverse_value = max(0, min(32768, reverse_value))
            self.vjoy_dev.data.wAxisXRot = reverse_value
            
            # Map prop to Y axis (0-32768)
            prop_value = int(prop * 327.68)  # 0,100 to 0,32768
            prop_value = max(0, min(32768, prop_value))
            self.vjoy_dev.data.wAxisY = prop_value
            
            # Map mixture to Z axis (0-32768)
            mixture_value = int(mixture * 327.68)  # 0,100 to 0,32768
            mixture_value = max(0, min(32768, mixture_value))
            self.vjoy_dev.data.wAxisZ = mixture_value
            
            # Update all axes at once
            self.vjoy_dev.update()
            
            # Print debug values occasionally
            if forward_value % 1000 == 0 or reverse_value % 1000 == 0:
                print(f"vJoy values - Forward: {forward_value}, Reverse: {reverse_value}, Prop/Speedbrake: {prop_value}, Mix: {mixture_value}")
                
            return forward_throttle, reverse_throttle, prop, mixture
                
        except Exception as e:
            print(f"vJoy update error: {str(e)}")
            return 0, 0, 0, 0

    def process_control_panel(self, pot_values):
        """Process control panel pot values and map to vJoy if needed"""
        if self.vjoy_dev is None:
            return pot_values
        
        processed_values = []
        
        # Check if controls are active
        controls_active = True
        if hasattr(self, 'controls_active'):
            controls_active = self.controls_active
        
        # Initialize button states dictionary if it doesn't exist
        if not hasattr(self, 'button_states'):
            self.button_states = {}
        
        # Initialize last pot values dictionary if it doesn't exist
        if not hasattr(self, 'last_pot_values'):
            self.last_pot_values = {}
        
        for i, raw_value in enumerate(pot_values):
            if i >= len(self.control_panel.pot_config):
                break
                
            config = self.control_panel.pot_config[i]
            
            # Skip processing if the value is invalid
            if raw_value is None:
                processed_values.append(0)
                continue
                
            processed = self.control_panel.process_pot_value(i, raw_value)
            processed_values.append(processed)
            
            # Only map to vJoy if controls are active
            if not controls_active:
                continue
            
            # Map to vJoy if configured as an axis
            if config['type'] == "Axis" and config['vjoy_axis'] is not None:
                # Map 0-100 to 0-32768
                axis_value = int(processed * 327.68)
                
                # Print debug info occasionally
                if int(raw_value) % 500 == 0 and hasattr(self, 'control_panel_debug_var') and self.control_panel_debug_var.get():
                    print(f"Mapping pot {i} ({config['name']}) to vJoy {config['vjoy_axis']} axis: {axis_value}")
                
                # Set the appropriate axis
                try:
                    if config['vjoy_axis'] == "X":
                        self.vjoy_dev.data.wAxisX = axis_value
                    elif config['vjoy_axis'] == "Y":
                        self.vjoy_dev.data.wAxisY = axis_value
                    elif config['vjoy_axis'] == "Z":
                        self.vjoy_dev.data.wAxisZ = axis_value
                    elif config['vjoy_axis'] == "RX":
                        self.vjoy_dev.data.wAxisXRot = axis_value
                    elif config['vjoy_axis'] == "RY":
                        self.vjoy_dev.data.wAxisYRot = axis_value
                    elif config['vjoy_axis'] == "RZ":
                        self.vjoy_dev.data.wAxisZRot = axis_value
                    elif config['vjoy_axis'] == "SL0":
                        self.vjoy_dev.data.wSlider = axis_value
                    elif config['vjoy_axis'] == "SL1":
                        self.vjoy_dev.data.wDial = axis_value
                except Exception as e:
                    print(f"Error setting vJoy axis {config['vjoy_axis']}: {str(e)}")
            
            # Handle button/switch mapping
            elif (config['type'] == "Switch" or config['type'] == "Button") and config['button_id'] is not None:
                try:
                    # Get button ID
                    button_id = int(config['button_id'])
                    
                    # Create a unique key for this pot/button combination
                    button_key = f"pot_{i}_button_{button_id}"
                    
                    # Get the current threshold state (above or below threshold)
                    current_threshold_state = processed > config['threshold']
                    
                    # Get the previous threshold state
                    previous_threshold_state = self.last_pot_values.get(button_key, False)
                    
                    # Determine button state based on control type
                    if config['type'] == "Switch":
                        # For Switch type, toggle the button state when crossing the threshold
                        if current_threshold_state != previous_threshold_state:
                            if current_threshold_state:  # Only toggle when crossing from below to above threshold
                                # Toggle the button state
                                current_button_state = self.button_states.get(button_key, 0)
                                new_button_state = 1 if current_button_state == 0 else 0
                                self.button_states[button_key] = new_button_state
                                
                                # Print debug info
                                if hasattr(self, 'control_panel_debug_var') and self.control_panel_debug_var.get():
                                    print(f"Switch {i} ({config['name']}) toggled to {new_button_state}")
                        
                        # Use the stored button state
                        button_state = self.button_states.get(button_key, 0)
                    else:  # Button type
                        # For Button type, directly use the threshold state
                        button_state = 1 if current_threshold_state else 0
                        
                        # Store the button state
                        self.button_states[button_key] = button_state
                    
                    # Store the current threshold state for next time
                    self.last_pot_values[button_key] = current_threshold_state
                    
                    # Print debug info occasionally
                    if int(raw_value) % 500 == 0 and hasattr(self, 'control_panel_debug_var') and self.control_panel_debug_var.get():
                        print(f"Pot {i} ({config['name']}) as {config['type']} mapped to button {button_id}: {button_state}")
                    
                    # Try to set the button using direct bit manipulation
                    try:
                        # Calculate which bit to set
                        bit_position = button_id - 1
                        button_mask = 1 << bit_position
                        
                        # Get current button state
                        current_buttons = self.vjoy_dev.data.lButtons
                        
                        # Set or clear the button bit
                        if button_state:
                            self.vjoy_dev.data.lButtons = current_buttons | button_mask
                        else:
                            self.vjoy_dev.data.lButtons = current_buttons & ~button_mask
                    except Exception as bit_error:
                        if hasattr(self, 'control_panel_debug_var') and self.control_panel_debug_var.get():
                            print(f"Error setting button bit: {str(bit_error)}")
                        
                        # Fall back to standard method
                        try:
                            self.vjoy_dev.set_button(button_id, button_state)
                        except Exception as button_error:
                            if hasattr(self, 'control_panel_debug_var') and self.control_panel_debug_var.get():
                                print(f"Error setting button {button_id}: {str(button_error)}")
                except Exception as e:
                    if hasattr(self, 'control_panel_debug_var') and self.control_panel_debug_var.get():
                        print(f"Error processing button mapping for pot {i}: {str(e)}")
        
        # Update vJoy device with all changes at once
        try:
            self.vjoy_dev.update()
        except Exception as e:
            print(f"Error updating vJoy: {str(e)}")
        
        return processed_values

class FlightControlGUI:
    def __init__(self):
        # Use ttkbootstrap instead of regular tk
        self.root = ttk.Window(
            themename='darkly' if darkdetect.isDark() else 'litera'
        )
        self.root.title("Flight Control Panel")
        self.root.geometry("800x600")
        
        # Add a style configuration
        self.style = ttk.Style()
        
        self.controls = FlightControls()
        self.running = True
        self.values_queue = queue.Queue()
        self.controls_active = True
        
        # Default COM port
        self.com_port = "COM11"
        
        # Store last raw values for calibration
        self.last_raw_values = {
            'throttle': 0,
            'reverse': 0,  # Same as throttle but used for reverse calibration
            'prop': 0,
            'mixture': 0
        }
        
        # Store last raw values for control panel
        self.last_control_panel_values = [0] * 7
        
        # Add a second COM port for control panel
        self.control_panel_com_port = "COM12"  # Default, can be changed by user
        
        # Create system tray icon
        self.icon = Image.new('RGB', (64, 64), color='red')
        self.tray_icon = pystray.Icon("flight_controls", self.icon, "Flight Controls", self.create_tray_menu())
        
        # Load settings if available
        self.settings_file = "flight_controls_settings.json"
        self.load_settings()
        
        # Initialize pot_frames list
        self.pot_frames = []
        
        # Initialize other control panel variables
        self.pot_name_vars = []
        self.pot_type_vars = []
        self.pot_inversion_vars = []
        self.pot_threshold_vars = []
        self.pot_axis_vars = []
        self.pot_button_vars = []
        
        self.create_widgets()
        self.start_serial_thread()
        
    def create_widgets(self):
        # Update the notebook style
        self.style.configure('TNotebook', tabposition='nw')
        self.style.configure('TNotebook.Tab', padding=[10, 5])
        
        # Create main container with padding
        main_container = ttk.Frame(self.root, padding="10")
        main_container.pack(fill=BOTH, expand=YES)
        
        # Create notebook for tabs
        self.notebook = ttk.Notebook(main_container)
        self.notebook.pack(fill=BOTH, expand=YES, padx=5, pady=5)
        
        # Create scrollable frames for both tabs
        main_tab = self.create_scrollable_frame(self.notebook)
        control_panel_tab = self.create_scrollable_frame(self.notebook)
        
        # Add tabs to notebook
        self.notebook.add(main_tab.frame, text="Main")
        self.notebook.add(control_panel_tab.frame, text="Control Panel")
        
        # All existing UI elements should use main_tab.scrolled_frame as parent
        # COM port selection frame
        com_frame = ttk.LabelFrame(main_tab.scrolled_frame, text="Connection Settings", padding="10")
        com_frame.pack(fill=X, pady=(0, 10))
        
        # Add COM port detection and selection
        def refresh_ports():
            ports = [port.device for port in serial.tools.list_ports.comports()]
            com_combo['values'] = ports
            if ports and self.com_port not in ports:
                self.com_port = ports[0]
                com_combo.set(self.com_port)
        
        port_frame = ttk.Frame(com_frame)
        port_frame.pack(fill=X)
        
        ttk.Label(port_frame, text="Throttle COM Port:").pack(side=LEFT, padx=(0, 5))
        com_combo = ttk.Combobox(port_frame, width=15)
        com_combo.pack(side=LEFT, padx=5)
        
        ttk.Button(
            port_frame, 
            text="Refresh", 
            command=refresh_ports,
            style='secondary.Outline.TButton'
        ).pack(side=LEFT, padx=5)
        
        ttk.Button(
            port_frame, 
            text="Connect",
            command=self.reconnect_serial,
            style='primary.TButton'
        ).pack(side=LEFT, padx=5)
        
        # Initialize port list
        refresh_ports()
        
        # Profile selection
        profile_frame = ttk.LabelFrame(main_tab.scrolled_frame, text="Profile", padding=10)
        profile_frame.pack(fill='x', padx=5, pady=5)
        
        self.profile_label = ttk.Label(profile_frame, text=self.controls.current_profile.value)
        self.profile_label.pack(side='left', padx=5)
        
        ttk.Button(profile_frame, text="Change Profile", command=self.next_profile).pack(side='right', padx=5)
        
        # Controller type selection
        controller_frame = ttk.LabelFrame(main_tab.scrolled_frame, text="Controller Type", padding=10)
        controller_frame.pack(fill='x', padx=5, pady=5)
        
        self.controller_var = tk.StringVar(value=self.controls.controller_type.value)
        
        # Create radio buttons for controller selection
        ttk.Radiobutton(
            controller_frame,
            text="Xbox Controller",
            variable=self.controller_var,
            value=ControllerType.XBOX.value,
            command=self.set_controller_type
        ).pack(side='left', padx=20)
        
        ttk.Radiobutton(
            controller_frame,
            text="vJoy Device",
            variable=self.controller_var,
            value=ControllerType.VJOY.value,
            command=self.set_controller_type
        ).pack(side='right', padx=20)
        
        # Control values
        values_frame = ttk.LabelFrame(main_tab.scrolled_frame, text="Control Values", padding=10)
        values_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Throttle (now split into forward and reverse)
        ttk.Label(values_frame, text="Forward Thrust:").grid(row=0, column=0, padx=5, pady=5)
        self.forward_bar = ttk.Progressbar(values_frame, length=200, mode='determinate')
        self.forward_bar.grid(row=0, column=1, padx=5, pady=5)
        self.forward_label = ttk.Label(values_frame, text="0%")
        self.forward_label.grid(row=0, column=2, padx=5, pady=5)
        
        ttk.Label(values_frame, text="Reverse Thrust:").grid(row=1, column=0, padx=5, pady=5)
        self.reverse_bar = ttk.Progressbar(values_frame, length=200, mode='determinate')
        self.reverse_bar.grid(row=1, column=1, padx=5, pady=5)
        self.reverse_label = ttk.Label(values_frame, text="0%")
        self.reverse_label.grid(row=1, column=2, padx=5, pady=5)
        
        # Prop
        ttk.Label(values_frame, text="Prop:").grid(row=2, column=0, padx=5, pady=5)
        self.prop_bar = ttk.Progressbar(values_frame, length=200, mode='determinate')
        self.prop_bar.grid(row=2, column=1, padx=5, pady=5)
        self.prop_label = ttk.Label(values_frame, text="0%")
        self.prop_label.grid(row=2, column=2, padx=5, pady=5)
        
        # Mixture
        ttk.Label(values_frame, text="Mixture:").grid(row=3, column=0, padx=5, pady=5)
        self.mixture_bar = ttk.Progressbar(values_frame, length=200, mode='determinate')
        self.mixture_bar.grid(row=3, column=1, padx=5, pady=5)
        self.mixture_label = ttk.Label(values_frame, text="0%")
        self.mixture_label.grid(row=3, column=2, padx=5, pady=5)
        
        # Add calibration frame with better layout and instructions
        cal_frame = ttk.LabelFrame(main_tab.scrolled_frame, text="Calibration", padding=10)
        cal_frame.pack(fill='x', padx=5, pady=5)
        
        # Add instructions
        instructions = """Calibration Instructions:
1. For Forward Thrust: Move throttle to idle position → Set Idle Point
   Then move to maximum forward → Set Max Forward
   
2. For Reverse Thrust: Move throttle to idle position → Set Idle Point
   Then move to maximum reverse → Set Max Reverse
   
3. For Prop/Speedbrake: Move to minimum position → Set Idle Point
   Then move to maximum position → Set Max Position
   
4. For Mixture: Move to minimum position → Set Idle Point
   Then move to maximum position → Set Max Position"""
        
        instruction_label = ttk.Label(cal_frame, text=instructions, justify='left')
        instruction_label.grid(row=0, column=0, columnspan=4, padx=5, pady=5, sticky='w')
        
        # Throttle calibration
        ttk.Label(cal_frame, text="Throttle:").grid(row=1, column=0, padx=5, pady=2, sticky='e')
        ttk.Button(cal_frame, text="Set Idle Point", 
                  command=lambda: self.set_idle_point('throttle')).grid(row=1, column=1, padx=5, pady=2)
        ttk.Button(cal_frame, text="Set Max Forward", 
                  command=lambda: self.set_max_forward()).grid(row=1, column=2, padx=5, pady=2)
        
        # Reverse calibration
        ttk.Label(cal_frame, text="Reverse:").grid(row=2, column=0, padx=5, pady=2, sticky='e')
        ttk.Button(cal_frame, text="Set Idle Point", 
                  command=lambda: self.set_idle_point('reverse')).grid(row=2, column=1, padx=5, pady=2)
        ttk.Button(cal_frame, text="Set Max Reverse", 
                  command=lambda: self.set_max_reverse()).grid(row=2, column=2, padx=5, pady=2)
        
        # Prop calibration
        prop_label_text = "Prop/Speedbrake:"
        ttk.Label(cal_frame, text=prop_label_text).grid(row=3, column=0, padx=5, pady=2, sticky='e')
        ttk.Button(cal_frame, text="Set Idle Point", 
                  command=lambda: self.set_idle_point('prop')).grid(row=3, column=1, padx=5, pady=2)
        ttk.Button(cal_frame, text="Set Max Position", 
                  command=lambda: self.set_max_position('prop')).grid(row=3, column=2, padx=5, pady=2)
        
        # Mixture calibration
        ttk.Label(cal_frame, text="Mixture:").grid(row=4, column=0, padx=5, pady=2, sticky='e')
        ttk.Button(cal_frame, text="Set Idle Point", 
                  command=lambda: self.set_idle_point('mixture')).grid(row=4, column=1, padx=5, pady=2)
        ttk.Button(cal_frame, text="Set Max Position", 
                  command=lambda: self.set_max_position('mixture')).grid(row=4, column=2, padx=5, pady=2)
        
        # Reset button
        ttk.Button(cal_frame, text="Reset All Calibration", 
                  command=self.reset_calibration).grid(row=5, column=0, columnspan=4, padx=5, pady=5)
        
        # Add calibration status display
        self.cal_status_frame = ttk.LabelFrame(main_tab.scrolled_frame, text="Calibration Status", padding=10)
        self.cal_status_frame.pack(fill='x', padx=5, pady=5)
        
        # Create labels to show current calibration values
        ttk.Label(self.cal_status_frame, text="Throttle Idle:").grid(row=0, column=0, padx=5, pady=2, sticky='e')
        self.throttle_idle_label = ttk.Label(self.cal_status_frame, text="0")
        self.throttle_idle_label.grid(row=0, column=1, padx=5, pady=2, sticky='w')
        
        ttk.Label(self.cal_status_frame, text="Throttle Max:").grid(row=0, column=2, padx=5, pady=2, sticky='e')
        self.throttle_max_label = ttk.Label(self.cal_status_frame, text="100")
        self.throttle_max_label.grid(row=0, column=3, padx=5, pady=2, sticky='w')
        
        ttk.Label(self.cal_status_frame, text="Reverse Idle:").grid(row=1, column=0, padx=5, pady=2, sticky='e')
        self.reverse_idle_label = ttk.Label(self.cal_status_frame, text="0")
        self.reverse_idle_label.grid(row=1, column=1, padx=5, pady=2, sticky='w')
        
        ttk.Label(self.cal_status_frame, text="Reverse Max:").grid(row=1, column=2, padx=5, pady=2, sticky='e')
        self.reverse_max_label = ttk.Label(self.cal_status_frame, text="0")
        self.reverse_max_label.grid(row=1, column=3, padx=5, pady=2, sticky='w')
        
        ttk.Label(self.cal_status_frame, text="Prop Idle:").grid(row=2, column=0, padx=5, pady=2, sticky='e')
        self.prop_idle_label = ttk.Label(self.cal_status_frame, text="0")
        self.prop_idle_label.grid(row=2, column=1, padx=5, pady=2, sticky='w')
        
        ttk.Label(self.cal_status_frame, text="Prop Max:").grid(row=2, column=2, padx=5, pady=2, sticky='e')
        self.prop_max_label = ttk.Label(self.cal_status_frame, text="100")
        self.prop_max_label.grid(row=2, column=3, padx=5, pady=2, sticky='w')
        
        ttk.Label(self.cal_status_frame, text="Mixture Idle:").grid(row=3, column=0, padx=5, pady=2, sticky='e')
        self.mixture_idle_label = ttk.Label(self.cal_status_frame, text="0")
        self.mixture_idle_label.grid(row=3, column=1, padx=5, pady=2, sticky='w')
        
        ttk.Label(self.cal_status_frame, text="Mixture Max:").grid(row=3, column=2, padx=5, pady=2, sticky='e')
        self.mixture_max_label = ttk.Label(self.cal_status_frame, text="100")
        self.mixture_max_label.grid(row=3, column=3, padx=5, pady=2, sticky='w')
        
        # Update calibration status display
        self.update_calibration_status()
        
        # Status label should be in main_container (outside notebook)
        self.status_label = ttk.Label(main_container, text="Connected", foreground="green")
        self.status_label.pack(pady=5)
        
        # Mapping info
        mapping_frame = ttk.LabelFrame(main_tab.scrolled_frame, text="Control Mapping", padding=10)
        mapping_frame.pack(fill='x', padx=5, pady=5)
        self.mapping_text = tk.Text(mapping_frame, height=4, width=40)
        self.mapping_text.pack(fill='x')
        self.update_mapping_text()
        
        # Add control toggle button
        control_frame = ttk.Frame(main_tab.scrolled_frame)
        control_frame.pack(fill='x', padx=5, pady=5)
        
        self.toggle_button = ttk.Button(
            control_frame, 
            text="Pause Controls", 
            command=self.toggle_controls
        )
        self.toggle_button.pack(side='left', padx=5)
        
        # Add keyboard shortcut label
        ttk.Label(
            control_frame, 
            text="Shortcut: Ctrl+Space"
        ).pack(side='left', padx=5)
        
        # Bind keyboard shortcut
        self.root.bind('<Control-space>', lambda e: self.toggle_controls())
        
        # Add axis inversion frame
        invert_frame = ttk.LabelFrame(main_tab.scrolled_frame, text="Control Settings", padding=10)
        invert_frame.pack(fill='x', padx=5, pady=5)
        
        # Create variables for checkboxes
        self.throttle_invert_var = tk.BooleanVar(value=self.controls.invert_axis['throttle'])
        self.prop_invert_var = tk.BooleanVar(value=self.controls.invert_axis['prop'])
        self.mixture_invert_var = tk.BooleanVar(value=self.controls.invert_axis['mixture'])
        self.reverse_invert_var = tk.BooleanVar(value=self.controls.invert_axis['reverse'])
        self.speedbrake_mode_var = tk.BooleanVar(value=self.controls.prop_as_speedbrake)
        
        # Create checkboxes for each axis
        ttk.Checkbutton(
            invert_frame, 
            text="Invert Throttle", 
            variable=self.throttle_invert_var,
            command=lambda: self.toggle_inversion('throttle')
        ).grid(row=0, column=0, padx=5, pady=2, sticky='w')
        
        ttk.Checkbutton(
            invert_frame, 
            text="Invert Prop", 
            variable=self.prop_invert_var,
            command=lambda: self.toggle_inversion('prop')
        ).grid(row=0, column=1, padx=5, pady=2, sticky='w')
        
        ttk.Checkbutton(
            invert_frame, 
            text="Invert Mixture", 
            variable=self.mixture_invert_var,
            command=lambda: self.toggle_inversion('mixture')
        ).grid(row=1, column=0, padx=5, pady=2, sticky='w')
        
        ttk.Checkbutton(
            invert_frame, 
            text="Invert Reverse", 
            variable=self.reverse_invert_var,
            command=lambda: self.toggle_inversion('reverse')
        ).grid(row=1, column=1, padx=5, pady=2, sticky='w')
        
        # Add speedbrake mode checkbox
        ttk.Checkbutton(
            invert_frame, 
            text="Use Prop as Speedbrake/Spoilers", 
            variable=self.speedbrake_mode_var,
            command=self.toggle_speedbrake_mode
        ).grid(row=2, column=0, columnspan=2, padx=5, pady=2, sticky='w')
        
        # Add save settings button
        settings_frame = ttk.Frame(main_tab.scrolled_frame)
        settings_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(
            settings_frame, 
            text="Save Settings", 
            command=self.save_settings
        ).pack(side='right', padx=5)
        
        # Create Control Panel UI in control_panel_tab.scrolled_frame
        self.create_control_panel_ui(control_panel_tab.scrolled_frame)
    
    def create_scrollable_frame(self, parent):
        """Create a scrollable frame and return both the container and scrolled frame"""
        # Create a class to hold the frames
        class ScrollableFrame:
            def __init__(self):
                self.frame = ttk.Frame(parent)
                
                # Create canvas
                self.canvas = tk.Canvas(self.frame)
                self.scrollbar = ttk.Scrollbar(self.frame, orient="vertical", command=self.canvas.yview)
                self.scrolled_frame = ttk.Frame(self.canvas)
                
                # Configure scrolling
                self.scrolled_frame.bind(
                    "<Configure>",
                    lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
                )
                
                # Create window in canvas
                self.canvas.create_window((0, 0), window=self.scrolled_frame, anchor="nw")
                self.canvas.configure(yscrollcommand=self.scrollbar.set)
                
                # Pack scrollbar and canvas
                self.scrollbar.pack(side="right", fill="y")
                self.canvas.pack(side="left", fill="both", expand=True)
                
                # Configure canvas size
                self.frame.bind("<Configure>", self.on_frame_configure)
                
                # Add mouse wheel scrolling
                self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)
            
            def on_frame_configure(self, event=None):
                self.canvas.configure(width=self.frame.winfo_width()-20)  # Adjust for scrollbar
            
            def on_mousewheel(self, event):
                self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        return ScrollableFrame()
    
    def set_pot_name(self, index, name):
        """Set the name for a potentiometer"""
        try:
            self.controls.control_panel.set_pot_name(index, name)
            self.pot_name_vars[index].set(name)
            # Save settings after changing pot name
            self.save_settings()
            return True
        except Exception as e:
            self.log_debug(f"Error setting pot name: {str(e)}")
            return False
    
    def set_pot_type(self, index, type_name):
        """Set the type for a potentiometer"""
        try:
            self.controls.control_panel.set_pot_type(index, type_name)
            self.pot_type_vars[index].set(type_name)
            # Save settings after changing pot type
            self.save_settings()
            return True
        except Exception as e:
            self.log_debug(f"Error setting pot type: {str(e)}")
            return False
    
    def toggle_pot_inversion(self, index):
        """Toggle inversion for a potentiometer"""
        try:
            self.controls.control_panel.toggle_pot_inversion(index)
            self.pot_inversion_vars[index].set(self.controls.control_panel.pot_config[index]["inversion"])
            # Save settings after toggling pot inversion
            self.save_settings()
            return True
        except Exception as e:
            self.log_debug(f"Error toggling pot inversion: {str(e)}")
            return False
    
    def set_pot_threshold(self, index, threshold):
        """Set threshold for a potentiometer"""
        try:
            self.controls.control_panel.set_pot_threshold(index, threshold)
            self.pot_threshold_vars[index].set(threshold)
            # Save settings after changing pot threshold
            self.save_settings()
            return True
        except Exception as e:
            self.log_debug(f"Error setting pot threshold: {str(e)}")
            return False
    
    def calibrate_pot_min(self, index):
        """Calibrate the minimum value for a potentiometer"""
        try:
            # Get the current value
            if index < len(self.pot_values):
                value = self.pot_values[index]
                if value is not None:
                    self.controls.control_panel.calibrate_pot_min(index, value)
                    self.log_debug(f"Pot {index} min calibrated to {value}")
                    # Save settings after calibration
                    self.save_settings()
                    return True
            return False
        except Exception as e:
            self.log_debug(f"Error calibrating pot min: {str(e)}")
            return False
    
    def calibrate_pot_max(self, index):
        """Calibrate the maximum value for a potentiometer"""
        try:
            # Get the current value
            if index < len(self.pot_values):
                value = self.pot_values[index]
                if value is not None:
                    self.controls.control_panel.calibrate_pot_max(index, value)
                    self.log_debug(f"Pot {index} max calibrated to {value}")
                    # Save settings after calibration
                    self.save_settings()
                    return True
            return False
        except Exception as e:
            self.log_debug(f"Error calibrating pot max: {str(e)}")
            return False
    
    def reconnect_control_panel(self):
        """Reconnect to control panel COM port"""
        # Update COM port and baud rate
        self.control_panel_com_port = self.control_panel_com_var.get()
        try:
            self.control_panel_baud_rate = int(self.control_panel_baud_var.get())
        except ValueError:
            self.control_panel_baud_rate = 115200  # Default if invalid
        
        # Restart control panel thread
        if hasattr(self, 'control_panel_running'):
            self.control_panel_running = False
            time.sleep(0.5)  # Give time for thread to stop
        
        self.control_panel_running = True
        self.start_control_panel_thread()
        
        self.status_label.config(text=f"Connecting to control panel on {self.control_panel_com_port} at {self.control_panel_baud_rate} baud...", foreground="blue")
    
    def start_control_panel_thread(self):
        """Start thread for reading from control panel"""
        def control_panel_loop():
            try:
                ser = serial.Serial(self.control_panel_com_port, self.control_panel_baud_rate, timeout=1)
                self.status_label.config(text=f"Connected to control panel on {self.control_panel_com_port}", foreground="green")
                
                # Clear any old data in the buffer
                ser.reset_input_buffer()
                
                while hasattr(self, 'control_panel_running') and self.control_panel_running:
                    if ser.in_waiting:
                        try:
                            line = ser.readline().decode('utf-8', errors='replace').strip()
                            
                            # Skip empty lines
                            if not line:
                                continue
                            
                            # Check if this is from the control panel
                            if not line.startswith("CTRLPANEL"):
                                continue
                            
                            # Remove the device identifier
                            line = line.replace("CTRLPANEL,", "")
                            
                            # Split the line into parts and filter out empty strings
                            parts = [p for p in line.split(',') if p.strip()]
                            
                            # Extract raw values (every other value)
                            raw_values = []
                            for i in range(0, min(14, len(parts)), 2):
                                try:
                                    raw_values.append(float(parts[i]))
                                except ValueError:
                                    raw_values.append(0)
                            
                            # Ensure we have 7 values
                            while len(raw_values) < 7:
                                raw_values.append(0)
                            
                            # Store raw values for calibration
                            self.last_control_panel_values = raw_values[:7]
                            
                            # Process values if controls are active
                            processed_values = self.controls.process_control_panel(raw_values[:7])
                            
                            # Update UI
                            for i, value in enumerate(processed_values):
                                if i < len(self.pot_frames):
                                    # Access dictionary values correctly
                                    self.pot_frames[i]['value_bar']['value'] = value
                                    self.pot_frames[i]['value_label'].config(text=f"{value:.0f}%")
                                    self.pot_frames[i]['raw_label'].config(text=f"Raw: {raw_values[i]:.0f}")
                    
                        except Exception as e:
                            print(f"Error processing control panel data: {str(e)}")
                            import traceback
                            traceback.print_exc()
                            
                    # Small sleep to prevent CPU hogging
                    time.sleep(0.01)
                            
            except serial.SerialException as e:
                print(f"Control panel connection error: {str(e)}")
                self.status_label.config(text=f"Control panel disconnected", foreground="red")
                
        threading.Thread(target=control_panel_loop, daemon=True).start()
    
    def start_serial_thread(self):
        def serial_loop():
            try:
                ser = serial.Serial(self.com_port, 115200, timeout=1)
                self.status_label.config(text=f"Connected to {self.com_port}", foreground="green")
                
                while self.running:
                    if ser.in_waiting:
                        try:
                            # Use errors='replace' to handle invalid UTF-8 bytes
                            line = ser.readline().decode('utf-8', errors='replace').strip()
                            
                            # Skip empty lines
                            if not line:
                                continue
                            
                            # Log raw data for debugging
                            self.log_debug(f"Raw data: '{line}'")
                            
                            # Split the line into parts and filter out empty strings
                            parts = [p for p in line.split(',') if p.strip()]
                            
                            # Handle different data formats more robustly
                            if len(parts) >= 6:
                                # Full format with raw and percentage values
                                try:
                                    t_raw, t_pct, p_raw, p_pct, m_raw, m_pct = map(float, parts[:6])
                                except ValueError:
                                    self.log_debug(f"Error parsing 6-value format: {parts[:6]}")
                                    continue
                            elif len(parts) >= 3:
                                # Only percentage values
                                try:
                                    t_pct, p_pct, m_pct = map(float, parts[:3])
                                except ValueError:
                                    self.log_debug(f"Error parsing 3-value format: {parts[:3]}")
                                    continue
                            else:
                                # Not enough data
                                self.log_debug(f"Unexpected data format: {line} (parts: {len(parts)})")
                                continue
                            
                            # Store raw values for calibration
                            self.last_raw_values['throttle'] = t_pct
                            self.last_raw_values['reverse'] = t_pct  # Same as throttle
                            self.last_raw_values['prop'] = p_pct
                            self.last_raw_values['mixture'] = m_pct
                            
                            # Only apply mapping if controls are active
                            if self.controls_active:
                                # Apply calibration and mapping - now returns 4 values
                                forward, reverse, p_cal, m_cal = self.controls.apply_mapping(t_pct, p_pct, m_pct)
                                self.values_queue.put((forward, reverse, p_cal, m_cal))
                            else:
                                # Still update the UI with raw values
                                # For raw values, we'll show forward if positive, reverse if negative
                                if t_pct >= 0:
                                    self.values_queue.put((t_pct, 0, p_pct, m_pct))
                                else:
                                    self.values_queue.put((0, -t_pct, p_pct, m_pct))
                        
                        except Exception as e:
                            print(f"Error processing serial data: {str(e)}")
                            # Add more detailed error information
                            import traceback
                            traceback.print_exc()
                            
                    # Small sleep to prevent CPU hogging
                    time.sleep(0.01)
                            
            except serial.SerialException as e:
                print(f"Serial connection error: {str(e)}")
                self.status_label.config(text="Disconnected", foreground="red")
                
        threading.Thread(target=serial_loop, daemon=True).start()
        self.update_gui()
        
        # Also start the control panel thread
        self.control_panel_running = True
        self.start_control_panel_thread()
    
    def update_gui(self):
        try:
            while not self.values_queue.empty():
                # Now we get four values: forward, reverse, prop, mixture
                forward, reverse, p_pct, m_pct = self.values_queue.get_nowait()
                
                # Update progress bars - ensure values are within range
                self.forward_bar['value'] = min(100, float(forward))
                self.reverse_bar['value'] = min(100, float(reverse))
                self.prop_bar['value'] = min(100, float(p_pct))
                self.mixture_bar['value'] = min(100, float(m_pct))
                
                # Update labels
                self.forward_label['text'] = f"{forward:.1f}%"
                self.reverse_label['text'] = f"{reverse:.1f}%"
                self.prop_label['text'] = f"{p_pct:.1f}%"
                self.mixture_label['text'] = f"{m_pct:.1f}%"
                
        except queue.Empty:
            pass
        except Exception as e:
            print(f"GUI update error: {str(e)}")
            
        if self.running:
            self.root.after(50, self.update_gui)
            
    def quit_application(self):
        # Save settings before quitting
        self.save_settings()
        
        self.running = False
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.quit()
        
    def run(self):
        self.root.mainloop()

    def toggle_debug(self):
        """Toggle debug mode to show raw serial data"""
        if hasattr(self, 'debug_mode') and self.debug_mode:
            self.debug_mode = False
            self.debug_window.destroy()
        else:
            self.debug_mode = True
            self.create_debug_window()

    def create_debug_window(self):
        """Create a debug window to show raw serial data"""
        self.debug_window = tk.Toplevel(self.root)
        self.debug_window.title("Serial Debug")
        self.debug_window.geometry("600x400")
        
        # Create a frame for the text and scrollbar
        text_frame = ttk.Frame(self.debug_window)
        text_frame.pack(fill='both', expand=True)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side='right', fill='y')
        
        # Create text widget with scrollbar
        self.debug_text = tk.Text(text_frame, yscrollcommand=scrollbar.set)
        self.debug_text.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=self.debug_text.yview)
        
        # Add buttons frame
        button_frame = ttk.Frame(self.debug_window)
        button_frame.pack(fill='x', pady=5)
        
        # Add a clear button
        ttk.Button(button_frame, text="Clear", 
                  command=lambda: self.debug_text.delete(1.0, tk.END)).pack(side='left', padx=5)
        
        # Add a "Parse Test" button to help diagnose data format
        ttk.Button(button_frame, text="Parse Test", 
                  command=self.test_parse_serial).pack(side='left', padx=5)
        
        # When window is closed, just toggle debug mode off
        self.debug_window.protocol('WM_DELETE_WINDOW', self.toggle_debug)

    def test_parse_serial(self):
        """Test parsing the last received serial data"""
        try:
            # Get the last line from the debug text
            last_line = self.debug_text.get("end-2l", "end-1l").strip()
            
            # Extract the raw data part
            if "Raw data:" in last_line:
                raw_data = last_line.split("Raw data: '")[1].rstrip("'")
                self._test_parse_throttle_data(raw_data)
            elif "Control Panel data:" in last_line:
                raw_data = last_line.split("Control Panel data: '")[1].rstrip("'")
                self._test_parse_control_panel_data(raw_data)
            else:
                self.log_debug("No raw data found in the last line.")
        except Exception as e:
            self.log_debug(f"Parse test error: {str(e)}")

    def _test_parse_throttle_data(self, raw_data):
        """Test parsing throttle quadrant data"""
        result = "Parsing Test Results (Throttle Quadrant):\n"
        result += f"Raw data: '{raw_data}'\n"
        
        # Split and filter parts
        parts = [p for p in raw_data.split(',') if p.strip()]
        result += f"Filtered parts ({len(parts)}): {parts}\n\n"
        
        # Try different parsing methods
        if len(parts) >= 6:
            try:
                t_raw, t_pct, p_raw, p_pct, m_raw, m_pct = map(float, parts[:6])
                result += f"6-value parse successful:\n"
                result += f"Throttle: raw={t_raw}, pct={t_pct}\n"
                result += f"Prop: raw={p_raw}, pct={p_pct}\n"
                result += f"Mixture: raw={m_raw}, pct={m_pct}\n"
            except ValueError as e:
                result += f"6-value parse failed: {str(e)}\n"
        
        if len(parts) >= 3:
            try:
                t_pct, p_pct, m_pct = map(float, parts[:3])
                result += f"3-value parse successful:\n"
                result += f"Throttle: {t_pct}%\n"
                result += f"Prop: {p_pct}%\n"
                result += f"Mixture: {m_pct}%\n"
            except ValueError as e:
                result += f"3-value parse failed: {str(e)}\n"
        
        # Display the results
        self.log_debug(result)

    def _test_parse_control_panel_data(self, raw_data):
        """Test parsing control panel data"""
        result = "Parsing Test Results (Control Panel):\n"
        result += f"Raw data: '{raw_data}'\n"
        
        # Check if it starts with CTRLPANEL
        if not raw_data.startswith("CTRLPANEL"):
            result += "Error: Data does not start with CTRLPANEL prefix\n"
            self.log_debug(result)
            return
        
        # Remove the device identifier
        data = raw_data.replace("CTRLPANEL,", "")
        
        # Split and filter parts
        parts = [p for p in data.split(',') if p.strip()]
        result += f"Filtered parts ({len(parts)}): {parts}\n\n"
        
        # Try to parse as raw and percentage values
        if len(parts) >= 14:
            try:
                result += "14-value parse (raw and percentage):\n"
                for i in range(0, 14, 2):
                    if i+1 < len(parts):
                        pot_num = i//2 + 1
                        raw = float(parts[i])
                        pct = float(parts[i+1])
                        result += f"Pot {pot_num}: raw={raw}, pct={pct}%\n"
            except ValueError as e:
                result += f"14-value parse failed: {str(e)}\n"
        
        # Try to parse as just raw values
        if len(parts) >= 7:
            try:
                result += "7-value parse (raw values only):\n"
                for i in range(7):
                    if i < len(parts):
                        pot_num = i + 1
                        raw = float(parts[i])
                        result += f"Pot {pot_num}: raw={raw}\n"
            except ValueError as e:
                result += f"7-value parse failed: {str(e)}\n"
        
        # Display the results
        self.log_debug(result)

    def log_debug(self, message):
        """Log a debug message if debug mode is on"""
        if hasattr(self, 'debug_mode') and self.debug_mode:
            self.debug_text.insert(tk.END, f"{message}\n")
            self.debug_text.see(tk.END)  # Scroll to end

    def toggle_inversion(self, axis):
        """Toggle inversion for the specified axis"""
        if axis == 'throttle':
            self.controls.invert_axis['throttle'] = self.throttle_invert_var.get()
        elif axis == 'prop':
            self.controls.invert_axis['prop'] = self.prop_invert_var.get()
        elif axis == 'mixture':
            self.controls.invert_axis['mixture'] = self.mixture_invert_var.get()
        elif axis == 'reverse':
            self.controls.invert_axis['reverse'] = self.reverse_invert_var.get()
            
        # Show confirmation message
        self.status_label.config(
            text=f"{axis.capitalize()} inversion {'enabled' if self.controls.invert_axis[axis] else 'disabled'}", 
            foreground="blue"
        )
        
        # Reset status after 2 seconds
        self.root.after(2000, lambda: self.status_label.config(
            text="Connected", foreground="green"
        ))

    def set_controller_type(self):
        """Set the controller type based on radio button selection"""
        selected_value = self.controller_var.get()
        
        # Find the enum value that matches the selected string
        for controller_type in ControllerType:
            if controller_type.value == selected_value:
                self.controls.controller_type = controller_type
                break
        
        # Update the mapping text to reflect the change
        self.update_mapping_text()
        
        # Show confirmation message
        self.status_label.config(
            text=f"Controller type set to {selected_value}", 
            foreground="blue"
        )
        
        # Reset status after 2 seconds
        self.root.after(2000, lambda: self.status_label.config(
            text="Connected", foreground="green"
        ))

    def load_settings(self):
        """Load settings from a JSON file"""
        try:
            # Check if settings file exists
            if not os.path.exists('settings/flight_controls.json'):
                self.log_debug("No settings file found")
                return
            
            # Load settings from file
            with open('settings/flight_controls.json', 'r') as f:
                settings = json.load(f)
            
            # Set profile
            if "profile" in settings and settings["profile"]:
                try:
                    self.controls.profile = ControlProfile[settings["profile"]]
                    self.update_mapping_text()
                except (KeyError, ValueError):
                    self.log_debug(f"Invalid profile: {settings['profile']}")
            
            # Set controller type
            if "controller_type" in settings and settings["controller_type"]:
                try:
                    self.controls.controller_type = ControllerType[settings["controller_type"]]
                    self.controller_type_var.set(self.controls.controller_type.value)
                except (KeyError, ValueError):
                    self.log_debug(f"Invalid controller type: {settings['controller_type']}")
            
            # Set inversions
            if "throttle_inversion" in settings:
                self.controls.throttle_inversion = settings["throttle_inversion"]
                self.throttle_inversion_var.set(self.controls.throttle_inversion)
            
            if "prop_inversion" in settings:
                self.controls.prop_inversion = settings["prop_inversion"]
                self.prop_inversion_var.set(self.controls.prop_inversion)
            
            if "mixture_inversion" in settings:
                self.controls.mixture_inversion = settings["mixture_inversion"]
                self.mixture_inversion_var.set(self.controls.mixture_inversion)
            
            # Set throttle calibration
            if "throttle_calibration" in settings:
                if "min" in settings["throttle_calibration"]:
                    self.controls.throttle_min = settings["throttle_calibration"]["min"]
                if "max" in settings["throttle_calibration"]:
                    self.controls.throttle_max = settings["throttle_calibration"]["max"]
                if "idle" in settings["throttle_calibration"]:
                    self.controls.throttle_idle = settings["throttle_calibration"]["idle"]
            
            # Set prop calibration
            if "prop_calibration" in settings:
                if "min" in settings["prop_calibration"]:
                    self.controls.prop_min = settings["prop_calibration"]["min"]
                if "max" in settings["prop_calibration"]:
                    self.controls.prop_max = settings["prop_calibration"]["max"]
            
            # Set mixture calibration
            if "mixture_calibration" in settings:
                if "min" in settings["mixture_calibration"]:
                    self.controls.mixture_min = settings["mixture_calibration"]["min"]
                if "max" in settings["mixture_calibration"]:
                    self.controls.mixture_max = settings["mixture_calibration"]["max"]
            
            # Set reverse calibration
            if "reverse_calibration" in settings:
                if "min" in settings["reverse_calibration"]:
                    self.controls.reverse_min = settings["reverse_calibration"]["min"]
                if "max" in settings["reverse_calibration"]:
                    self.controls.reverse_max = settings["reverse_calibration"]["max"]
            
            # Set speedbrake mode
            if "speedbrake_mode" in settings:
                self.controls.speedbrake_mode = settings["speedbrake_mode"]
                self.speedbrake_mode_var.set(self.controls.speedbrake_mode)
            
            # Set controls active
            if "controls_active" in settings:
                self.controls.controls_active = settings["controls_active"]
                self.controls_active_var.set(self.controls.controls_active)
            
            # Load control panel configuration
            if "control_panel" in settings and "pot_config" in settings["control_panel"]:
                for i, pot_settings in enumerate(settings["control_panel"]["pot_config"]):
                    if i >= len(self.controls.control_panel.pot_config):
                        break
                    
                    # Update pot configuration
                    if "name" in pot_settings:
                        self.controls.control_panel.set_pot_name(i, pot_settings["name"])
                        # Update UI
                        if hasattr(self, 'pot_name_vars') and i < len(self.pot_name_vars):
                            self.pot_name_vars[i].set(pot_settings["name"])
                    
                    if "type" in pot_settings:
                        self.controls.control_panel.set_pot_type(i, pot_settings["type"])
                        # Update UI
                        if hasattr(self, 'pot_type_vars') and i < len(self.pot_type_vars):
                            self.pot_type_vars[i].set(pot_settings["type"])
                    
                    if "threshold" in pot_settings:
                        self.controls.control_panel.set_pot_threshold(i, pot_settings["threshold"])
                        # Update UI
                        if hasattr(self, 'pot_threshold_vars') and i < len(self.pot_threshold_vars):
                            self.pot_threshold_vars[i].set(pot_settings["threshold"])
                    
                    if "inversion" in pot_settings:
                        # Set inversion to match saved value
                        if self.controls.control_panel.pot_config[i]["inversion"] != pot_settings["inversion"]:
                            self.controls.control_panel.toggle_pot_inversion(i)
                        # Update UI
                        if hasattr(self, 'pot_inversion_vars') and i < len(self.pot_inversion_vars):
                            self.pot_inversion_vars[i].set(pot_settings["inversion"])
                    
                    if "min" in pot_settings:
                        self.controls.control_panel.calibrate_pot_min(i, pot_settings["min"])
                    
                    if "max" in pot_settings:
                        self.controls.control_panel.calibrate_pot_max(i, pot_settings["max"])
                    
                    if "vjoy_axis" in pot_settings:
                        # Update pot configuration directly
                        self.controls.control_panel.pot_config[i]["vjoy_axis"] = pot_settings["vjoy_axis"]
                        # Update UI
                        if hasattr(self, 'pot_axis_vars') and i < len(self.pot_axis_vars):
                            self.pot_axis_vars[i].set(pot_settings["vjoy_axis"] if pot_settings["vjoy_axis"] else "None")
                    
                    if "button_id" in pot_settings:
                        # Update pot configuration directly
                        self.controls.control_panel.pot_config[i]["button_id"] = pot_settings["button_id"]
                        # Update UI
                        if hasattr(self, 'pot_button_vars') and i < len(self.pot_button_vars):
                            self.pot_button_vars[i].set(pot_settings["button_id"] if pot_settings["button_id"] else "")
            
            # Load button states for toggle switches
            if "button_states" in settings:
                self.controls.button_states = settings["button_states"]
            else:
                # Initialize empty button states dictionary if not present
                self.controls.button_states = {}
            
            # Update UI
            self.update_calibration_status()
            self.update_mapping_text()
            
            self.log_debug("Settings loaded successfully")
        except Exception as e:
            self.log_debug(f"Error loading settings: {str(e)}")
    
    def save_settings(self):
        """Save all settings to a JSON file"""
        try:
            settings = {
                "profile": self.controls.current_profile.name if self.controls.current_profile else None,
                "controller_type": self.controls.controller_type.name if self.controls.controller_type else None,
                "throttle_inversion": self.controls.invert_axis['throttle'],
                "prop_inversion": self.controls.invert_axis['prop'],
                "mixture_inversion": self.controls.invert_axis['mixture'],
                "throttle_calibration": {
                    "min": self.controls.calibration['throttle']['min'],
                    "max": self.controls.calibration['throttle']['max'],
                    "idle": self.controls.calibration['throttle']['idle']
                },
                "prop_calibration": {
                    "min": self.controls.calibration['prop']['min'],
                    "max": self.controls.calibration['prop']['max']
                },
                "mixture_calibration": {
                    "min": self.controls.calibration['mixture']['min'],
                    "max": self.controls.calibration['mixture']['max']
                },
                "reverse_calibration": {
                    "min": self.controls.calibration['reverse']['min'],
                    "max": self.controls.calibration['reverse']['max']
                },
                "speedbrake_mode": self.controls.prop_as_speedbrake,
                "controls_active": self.controls_active if hasattr(self.controls, 'controls_active') else True,
                # Save control panel configuration
                "control_panel": {
                    "pot_config": []
                }
            }
            
            # Save each potentiometer configuration
            for i, config in enumerate(self.controls.control_panel.pot_config):
                pot_settings = {
                    "name": config["name"],
                    "type": config["type"],
                    "threshold": config["threshold"],
                    "inversion": config["inversion"],
                    "min": config["min"],
                    "max": config["max"],
                    "vjoy_axis": config["vjoy_axis"],
                    "button_id": config["button_id"]
                }
                settings["control_panel"]["pot_config"].append(pot_settings)
            
            # Save button states for toggle switches
            if hasattr(self.controls, 'button_states'):
                settings["button_states"] = self.controls.button_states
            
            # Create settings directory if it doesn't exist
            os.makedirs('settings', exist_ok=True)
            
            # Save to file
            with open('settings/flight_controls.json', 'w') as f:
                json.dump(settings, f, indent=4)
                
            self.log_debug("Settings saved successfully")
        except Exception as e:
            self.log_debug(f"Error saving settings: {str(e)}")

    def minimize_to_tray(self):
        """Minimize the application to system tray"""
        self.root.withdraw()
        threading.Thread(target=self.tray_icon.run, daemon=True).start()
    
    def show_window(self):
        """Show the window from system tray"""
        self.tray_icon.stop()
        self.root.deiconify()
    
    def create_tray_menu(self):
        """Create the system tray menu"""
        return pystray.Menu(
            pystray.MenuItem("Show", self.show_window),
            pystray.MenuItem("Exit", self.quit_application)
        )

    def next_profile(self):
        """Change to the next control profile"""
        new_profile = self.controls.next_profile()
        self.profile_label.config(text=new_profile.value)
        self.update_mapping_text()
        return new_profile

    def reset_calibration(self):
        """Reset all calibration to defaults"""
        # Get the current raw values to set as the idle points
        throttle_value = self.last_raw_values['throttle']
        prop_value = self.last_raw_values['prop']
        mixture_value = self.last_raw_values['mixture']
        
        self.controls.calibration = {
            'throttle': {'min': 0, 'max': 100, 'idle': throttle_value},
            'reverse': {'min': 0, 'max': 100, 'idle': throttle_value},
            'prop': {'min': 0, 'max': 100, 'idle': prop_value},
            'mixture': {'min': 0, 'max': 100, 'idle': mixture_value}
        }
        
        # Update calibration status display
        self.update_calibration_status()
        
        self.status_label.config(
            text=f"Calibration reset. Current positions set as idle points.",
            foreground="blue"
        )
        
        # Reset status after 2 seconds
        self.root.after(2000, lambda: self.status_label.config(
            text="Connected", foreground="green"
        ))

    def update_mapping_text(self):
        """Update the mapping text based on current profile and controller type"""
        self.mapping_text.delete(1.0, tk.END)
        
        # Define mappings for all profiles
        prop_text = "Speedbrake/Spoilers" if self.controls.prop_as_speedbrake else "Prop"
        
        # Different mappings based on controller type
        if self.controls.controller_type == ControllerType.VJOY:
            # vJoy mappings are the same for all profiles
            mapping = f"""vJoy Device Mapping:
Forward Thrust: vJoy X-Axis
Reverse Thrust: vJoy XRot-Axis
{prop_text}: vJoy Y-Axis
Mixture: vJoy Z-Axis

Note: In your simulator's controls:
1. Select 'vJoy Device' in controller options
2. Bind axes as follows:
   - Forward Throttle -> X Axis
   - Reverse Throttle -> XRot Axis
   - {prop_text} -> Y Axis
   - Mixture -> Z Axis"""
        else:
            # Xbox controller mappings vary by profile
            mappings = {
                ControlProfile.MSFS: f"""Throttle: Right/Left Triggers
{prop_text}: Right Stick Y
Mixture: Left Stick Y""",
                
                ControlProfile.DCS: f"""Throttle: Left Stick Y
{prop_text}: Left Stick X
Mixture: Right Stick Y""",
                
                ControlProfile.XPLANE: f"""Throttle: Right/Left Triggers
{prop_text}: Right Stick Y
Mixture: Right Stick X""",
                
                ControlProfile.IL2: f"""Throttle: Left Stick Y
{prop_text}: Right Trigger
Mixture: Left Trigger""",
                
                ControlProfile.WAR_THUNDER: f"""War Thunder Setup (Xbox):
Throttle: Right/Left Triggers
{prop_text}: Right Stick Y
Mixture: Left Stick Y"""
            }
            
            # Get mapping for current profile, or use default text if not found
            mapping = mappings.get(
                self.controls.current_profile,
                "Profile mapping not defined"
            )
        
        self.mapping_text.insert(1.0, mapping)

    def update_calibration_status(self):
        """Update the calibration status display"""
        # Update throttle calibration labels
        self.throttle_idle_label.config(text=str(self.controls.calibration['throttle']['idle']))
        self.throttle_max_label.config(text=str(self.controls.calibration['throttle']['max']))
        
        # Update reverse calibration labels
        self.reverse_idle_label.config(text=str(self.controls.calibration['reverse']['idle']))
        self.reverse_max_label.config(text=str(self.controls.calibration['reverse']['min']))
        
        # Update prop calibration labels
        self.prop_idle_label.config(text=str(self.controls.calibration['prop']['idle']))
        self.prop_max_label.config(text=str(self.controls.calibration['prop']['max']))
        
        # Update mixture calibration labels
        self.mixture_idle_label.config(text=str(self.controls.calibration['mixture']['idle']))
        self.mixture_max_label.config(text=str(self.controls.calibration['mixture']['max']))

    def set_idle_point(self, control_type):
        """Set the idle point for a control"""
        raw_value = self.last_raw_values[control_type]
        
        # Set the idle point
        self.controls.calibration[control_type]['idle'] = raw_value
        
        # Show confirmation message
        control_name = control_type.capitalize()
        self.status_label.config(
            text=f"{control_name} idle point set to {raw_value}", 
            foreground="blue"
        )
        
        # Update calibration status display
        self.update_calibration_status()
        
        # Reset status after 2 seconds
        self.root.after(2000, lambda: self.status_label.config(
            text="Connected", foreground="green"
        ))

    def set_max_forward(self):
        """Set the maximum forward throttle point"""
        raw_value = self.last_raw_values['throttle']
        
        # Set the max point for throttle
        self.controls.calibration['throttle']['max'] = raw_value
        
        # Show confirmation message
        self.status_label.config(
            text=f"Maximum forward throttle set to {raw_value}", 
            foreground="blue"
        )
        
        # Update calibration status display
        self.update_calibration_status()
        
        # Reset status after 2 seconds
        self.root.after(2000, lambda: self.status_label.config(
            text="Connected", foreground="green"
        ))

    def set_max_reverse(self):
        """Set the maximum reverse throttle point"""
        raw_value = self.last_raw_values['throttle']
        
        # Set the min point for reverse
        self.controls.calibration['reverse']['min'] = raw_value
        
        # Show confirmation message
        self.status_label.config(
            text=f"Maximum reverse throttle set to {raw_value}", 
            foreground="blue"
        )
        
        # Update calibration status display
        self.update_calibration_status()
        
        # Reset status after 2 seconds
        self.root.after(2000, lambda: self.status_label.config(
            text="Connected", foreground="green"
        ))

    def set_max_position(self, control_type):
        """Set the maximum position for prop or mixture"""
        raw_value = self.last_raw_values[control_type]
        
        # Set the max point
        self.controls.calibration[control_type]['max'] = raw_value
        
        # Show confirmation message
        control_name = "Speedbrake" if control_type == 'prop' and self.controls.prop_as_speedbrake else control_type.capitalize()
        self.status_label.config(
            text=f"Maximum {control_name} position set to {raw_value}", 
            foreground="blue"
        )
        
        # Update calibration status display
        self.update_calibration_status()
        
        # Reset status after 2 seconds
        self.root.after(2000, lambda: self.status_label.config(
            text="Connected", foreground="green"
        ))

    def toggle_speedbrake_mode(self):
        """Toggle between prop and speedbrake mode"""
        self.controls.prop_as_speedbrake = self.speedbrake_mode_var.get()
        
        mode_text = "Speedbrake/Spoilers" if self.controls.prop_as_speedbrake else "Prop"
        self.status_label.config(
            text=f"Prop control now functions as {mode_text}", 
            foreground="blue"
        )
        
        # Update the mapping text to reflect the change
        self.update_mapping_text()
        
        # Reset status after 2 seconds
        self.root.after(2000, lambda: self.status_label.config(
            text="Connected", foreground="green"
        ))

    def toggle_controls(self):
        """Toggle controls active/inactive"""
        self.controls_active = not self.controls_active
        if self.controls_active:
            self.toggle_button.config(text="Pause Controls")
            self.status_label.config(text="Controls Active", foreground="green")
        else:
            self.toggle_button.config(text="Resume Controls")
            self.status_label.config(text="Controls Paused", foreground="orange")
            
        # Reset gamepad to neutral when pausing
        if not self.controls_active:
            self.controls.gamepad.reset()
            self.controls.gamepad.update()

    def reconnect_serial(self):
        """Reconnect to serial port with new COM port"""
        # Update COM port
        self.com_port = self.com_var.get()
        
        # Restart serial thread
        self.running = False
        time.sleep(0.5)  # Give time for thread to stop
        self.running = True
        self.start_serial_thread()
        
        self.status_label.config(text=f"Connecting to {self.com_port}...", foreground="blue")

    def reset_control_panel_connection(self):
        """Reset the control panel connection"""
        if hasattr(self, 'control_panel_running'):
            self.control_panel_running = False
            time.sleep(0.5)  # Give time for thread to stop
        
        # Clear any stored values
        self.last_control_panel_values = [0] * 7
        
        # Restart the thread
        self.control_panel_running = True
        self.start_control_panel_thread()
        
        self.status_label.config(text=f"Resetting control panel connection...", foreground="blue")

    def open_pot_calibration_tool(self):
        """Open a tool to help calibrate the potentiometers"""
        if hasattr(self, 'calibration_window') and self.calibration_window.winfo_exists():
            self.calibration_window.lift()
            return
            
        self.calibration_window = tk.Toplevel(self.root)
        self.calibration_window.title("Potentiometer Calibration Tool")
        self.calibration_window.geometry("800x600")
        
        # Create a frame for the controls
        control_frame = ttk.Frame(self.calibration_window, padding=10)
        control_frame.pack(fill='x', padx=5, pady=5)
        
        # Add a button to capture min/max values
        self.capturing_minmax = False
        self.capture_button = ttk.Button(
            control_frame, 
            text="Start Capturing Min/Max", 
            command=self.toggle_capture_minmax
        )
        self.capture_button.pack(side='left', padx=5)
        
        # Add a button to reset min/max values
        ttk.Button(
            control_frame, 
            text="Reset Min/Max", 
            command=self.reset_pot_minmax
        ).pack(side='left', padx=5)
        
        # Add a button to apply calibration
        ttk.Button(
            control_frame, 
            text="Apply Calibration", 
            command=self.apply_pot_calibration
        ).pack(side='right', padx=5)
        
        # Create a frame for the potentiometer displays
        pots_frame = ttk.Frame(self.calibration_window, padding=10)
        pots_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Create a canvas for the potentiometer values
        self.pot_canvas = tk.Canvas(pots_frame, bg='white')
        self.pot_canvas.pack(fill='both', expand=True)
        
        # Create labels for each potentiometer
        self.pot_labels = []
        for i in range(7):
            label = ttk.Label(
                pots_frame, 
                text=f"Pot {i+1}: 0", 
                font=('Arial', 12)
            )
            label.place(x=10, y=10 + i*30)
            self.pot_labels.append(label)
        
        # Initialize min/max values
        self.pot_min_values = [1023] * 7
        self.pot_max_values = [0] * 7
        
        # Start updating the display
        self.update_calibration_display()

    def toggle_capture_minmax(self):
        """Toggle capturing min/max values"""
        self.capturing_minmax = not self.capturing_minmax
        if self.capturing_minmax:
            self.capture_button.config(text="Stop Capturing Min/Max")
        else:
            self.capture_button.config(text="Start Capturing Min/Max")
            
            # Log the captured values
            min_values_str = ", ".join([str(v) for v in self.pot_min_values])
            max_values_str = ", ".join([str(v) for v in self.pot_max_values])
            self.log_debug(f"Captured Min Values: [{min_values_str}]")
            self.log_debug(f"Captured Max Values: [{max_values_str}]")

    def reset_pot_minmax(self):
        """Reset min/max values for potentiometers"""
        self.pot_min_values = [1023] * 7
        self.pot_max_values = [0] * 7
        self.log_debug("Reset min/max values for all potentiometers")

    def apply_pot_calibration(self):
        """Apply the captured min/max values to the potentiometer calibration"""
        for i in range(7):
            self.controls.control_panel.pot_config[i]['calibrated_min'] = self.pot_min_values[i]
            self.controls.control_panel.pot_config[i]['calibrated_max'] = self.pot_max_values[i]
        
        self.log_debug("Applied calibration to all potentiometers")
        
        # Update the status
        self.status_label.config(text="Potentiometer calibration applied", foreground="blue")
        self.root.after(2000, lambda: self.status_label.config(text="Connected", foreground="green"))

    def update_calibration_display(self):
        """Update the calibration display"""
        if hasattr(self, 'calibration_window') and self.calibration_window.winfo_exists():
            # Clear the canvas
            self.pot_canvas.delete("all")
            
            # Draw the potentiometer values
            for i, value in enumerate(self.last_control_panel_values):
                # Update min/max if capturing
                if self.capturing_minmax:
                    if value < self.pot_min_values[i]:
                        self.pot_min_values[i] = value
                    if value > self.pot_max_values[i]:
                        self.pot_max_values[i] = value
                
                # Calculate position
                x_pos = 50 + (i * 100)
                y_pos = 300
                
                # Draw the potentiometer
                self.pot_canvas.create_oval(x_pos-40, y_pos-40, x_pos+40, y_pos+40, fill='lightgray')
                
                # Draw the indicator line
                angle = (value / 1023) * 270 - 135  # -135 to 135 degrees
                rad_angle = math.radians(angle)
                end_x = x_pos + 35 * math.cos(rad_angle)
                end_y = y_pos + 35 * math.sin(rad_angle)
                self.pot_canvas.create_line(x_pos, y_pos, end_x, end_y, width=3, fill='red')
                
                # Draw the value
                self.pot_canvas.create_text(x_pos, y_pos+50, text=f"{value:.0f}", font=('Arial', 10))
                
                # Draw the min/max values
                self.pot_canvas.create_text(x_pos, y_pos+70, 
                                           text=f"Min: {self.pot_min_values[i]:.0f}", 
                                           font=('Arial', 8))
                self.pot_canvas.create_text(x_pos, y_pos+85, 
                                           text=f"Max: {self.pot_max_values[i]:.0f}", 
                                           font=('Arial', 8))
                
                # Update the label
                self.pot_labels[i].config(text=f"Pot {i+1}: {value:.0f} (Min: {self.pot_min_values[i]:.0f}, Max: {self.pot_max_values[i]:.0f})")
            
            # Schedule the next update
            self.calibration_window.after(50, self.update_calibration_display)

    def set_pot_vjoy_axis(self, index, axis_name):
        """Set the vJoy axis for a potentiometer"""
        try:
            # Convert "None" to None
            if axis_name == "None":
                axis_name = None
            
            # Update the pot configuration
            self.controls.control_panel.pot_config[index]["vjoy_axis"] = axis_name
            
            # Update the UI
            self.pot_axis_vars[index].set(axis_name if axis_name else "None")
            
            # Test the axis if a valid axis is selected
            if axis_name and self.controls.vjoy_dev:
                try:
                    # Get the current pot value
                    pot_value = self.controls.control_panel.pot_config[index]["last_value"]
                    if pot_value is not None:
                        # Process the pot value
                        processed = self.controls.control_panel.process_pot_value(index, pot_value)
                        
                        # Map 0-100 to 0-32768
                        axis_value = int(processed * 327.68)
                        
                        # Set the appropriate axis
                        if axis_name == "X":
                            self.controls.vjoy_dev.data.wAxisX = axis_value
                        elif axis_name == "Y":
                            self.controls.vjoy_dev.data.wAxisY = axis_value
                        elif axis_name == "Z":
                            self.controls.vjoy_dev.data.wAxisZ = axis_value
                        elif axis_name == "RX":
                            self.controls.vjoy_dev.data.wAxisXRot = axis_value
                        elif axis_name == "RY":
                            self.controls.vjoy_dev.data.wAxisYRot = axis_value
                        elif axis_name == "RZ":
                            self.controls.vjoy_dev.data.wAxisZRot = axis_value
                        elif axis_name == "SL0":
                            self.controls.vjoy_dev.data.wSlider = axis_value
                        elif axis_name == "SL1":
                            self.controls.vjoy_dev.data.wDial = axis_value
                        
                        # Update vJoy
                        self.controls.vjoy_dev.update()
                        
                        # Show confirmation
                        self.log_debug(f"Pot {index} mapped to vJoy {axis_name} axis with value {axis_value}")
                except Exception as e:
                    self.log_debug(f"Error testing axis: {str(e)}")
            
            # Save settings after changing axis mapping
            self.save_settings()
            
            return True
        except Exception as e:
            self.log_debug(f"Error setting vJoy axis: {str(e)}")
            return False

    def reset_axis(self, axis_name):
        """Reset a vJoy axis to 0"""
        if hasattr(self.controls, 'vjoy_dev') and self.controls.vjoy_dev is not None:
            try:
                if axis_name == "X":
                    self.controls.vjoy_dev.data.wAxisX = 0
                elif axis_name == "Y":
                    self.controls.vjoy_dev.data.wAxisY = 0
                elif axis_name == "Z":
                    self.controls.vjoy_dev.data.wAxisZ = 0
                elif axis_name == "RX":
                    self.controls.vjoy_dev.data.wAxisXRot = 0
                elif axis_name == "RY":
                    self.controls.vjoy_dev.data.wAxisYRot = 0
                elif axis_name == "RZ":
                    self.controls.vjoy_dev.data.wAxisZRot = 0
                elif axis_name == "SL0":
                    self.controls.vjoy_dev.data.wSlider = 0
                elif axis_name == "SL1":
                    self.controls.vjoy_dev.data.wDial = 0
                
                self.controls.vjoy_dev.update()
            except Exception as e:
                print(f"Error resetting axis {axis_name}: {str(e)}")

    def set_pot_button_id(self, index, button_id):
        """Set the button ID for a potentiometer"""
        try:
            # Convert empty string to None
            if not button_id:
                button_id = None
            
            # Update the pot configuration
            self.controls.control_panel.pot_config[index]["button_id"] = button_id
            
            # Update the UI
            self.pot_button_vars[index].set(button_id if button_id else "")
            
            # Test the button if a valid button ID is provided
            if button_id and self.controls.vjoy_dev:
                try:
                    # Convert button ID to integer
                    button_id_int = int(button_id)
                    
                    # Try to press the button using bit manipulation
                    try:
                        # Calculate which bit to set
                        bit_position = button_id_int - 1
                        button_mask = 1 << bit_position
                        
                        # Get current button state
                        current_buttons = self.controls.vjoy_dev.data.lButtons
                        
                        # Set the button bit
                        self.controls.vjoy_dev.data.lButtons = current_buttons | button_mask
                        self.controls.vjoy_dev.update()
                        
                        # Schedule to release the button after 500ms
                        self.root.after(500, lambda: self.release_button_bit(button_id_int))
                        
                        # Show confirmation
                        self.log_debug(f"Pot {index} mapped to button {button_id_int} (using bit manipulation)")
                    except Exception as bit_error:
                        self.log_debug(f"Bit manipulation failed: {str(bit_error)}")
                        
                        # Try standard method as fallback
                        self.controls.vjoy_dev.set_button(button_id_int, 1)
                        self.controls.vjoy_dev.update()
                        
                        # Schedule to release the button after 500ms
                        self.root.after(500, lambda: self.release_test_button(button_id_int))
                        
                        # Show confirmation
                        self.log_debug(f"Pot {index} mapped to button {button_id_int} (using standard method)")
                except ValueError:
                    self.log_debug(f"Invalid button ID: {button_id}")
                    return False
                except Exception as e:
                    self.log_debug(f"Error setting button ID: {str(e)}")
                    return False
            
            # Save settings after changing button mapping
            self.save_settings()
            
            return True
        
        except Exception as e:
            self.log_debug(f"Error setting button ID: {str(e)}")
            return False

    def release_button_bit(self, button_id):
        """Release a button using bit manipulation"""
        try:
            # Calculate which bit to clear
            bit_position = button_id - 1
            button_mask = 1 << bit_position
            
            # Get current button state
            current_buttons = self.controls.vjoy_dev.data.lButtons
            
            # Clear the button bit
            self.controls.vjoy_dev.data.lButtons = current_buttons & ~button_mask
            self.controls.vjoy_dev.update()
            print(f"Button {button_id} released using bit manipulation")
        except Exception as e:
            print(f"Error releasing button bit: {str(e)}")

    def test_vjoy_button(self, index):
        """Test a vJoy button by toggling it on and off"""
        if not hasattr(self.controls, 'vjoy_dev') or self.controls.vjoy_dev is None:
            self.status_label.config(text="vJoy device not available", foreground="red")
            return
            
        try:
            # Get the button ID
            button_id = self.controls.control_panel.pot_config[index]['button_id']
            if button_id is None:
                self.status_label.config(text=f"No button ID set for pot {index+1}", foreground="red")
                return
                
            # Convert to integer
            button_id = int(button_id)
            
            # Show testing message
            self.status_label.config(text=f"Testing button {button_id}...", foreground="blue")
            
            # Try to press the button using bit manipulation
            try:
                # Calculate which bit to set
                bit_position = button_id - 1
                button_mask = 1 << bit_position
                
                # Get current button state
                current_buttons = self.controls.vjoy_dev.data.lButtons
                
                # Press the button
                self.controls.vjoy_dev.data.lButtons = current_buttons | button_mask
                self.controls.vjoy_dev.update()
                print(f"Button {button_id} pressed using bit manipulation")
                
                # Schedule to release the button after 500ms
                self.root.after(500, lambda: self.release_button_bit(button_id))
                
                # Show success message
                self.status_label.config(text=f"Button {button_id} pressed (bit manipulation)", foreground="blue")
            except Exception as bit_error:
                print(f"Bit manipulation failed: {str(bit_error)}")
                
                # Try standard method as fallback
                try:
                    self.controls.vjoy_dev.set_button(button_id, 1)
                    self.controls.vjoy_dev.update()
                    print(f"Button {button_id} pressed using standard method")
                    
                    # Schedule to release the button after 500ms
                    self.root.after(500, lambda: self.release_test_button(button_id))
                    
                    # Show success message
                    self.status_label.config(text=f"Button {button_id} pressed (standard method)", foreground="blue")
                except Exception as std_error:
                    self.status_label.config(text=f"All button methods failed: {str(std_error)}", foreground="red")
                    print(f"Standard method failed: {str(std_error)}")
        except Exception as e:
            self.status_label.config(text=f"Button test error: {str(e)}", foreground="red")
            print(f"Button test error: {str(e)}")

    def release_test_button(self, button_id):
        """Release a test button"""
        try:
            self.controls.vjoy_dev.set_button(button_id, 0)
            self.controls.vjoy_dev.update()
            self.status_label.config(text=f"Button {button_id} released", foreground="green")
        except Exception as e:
            self.status_label.config(text=f"Button release error: {str(e)}", foreground="red")
            print(f"Button release error: {str(e)}")
            
            # Try alternative method
            try:
                self.release_test_button_alt(button_id)
            except Exception as alt_error:
                print(f"Alternative button release failed: {str(alt_error)}")

    def release_test_button_alt(self, button_id):
        """Release a test button using alternative method"""
        try:
            if hasattr(self.controls.vjoy_dev.data, 'lButtons'):
                # Calculate which bit to clear
                bit_position = button_id - 1
                button_mask = 1 << bit_position
                
                # Clear the button bit
                current_buttons = self.controls.vjoy_dev.data.lButtons
                self.controls.vjoy_dev.data.lButtons = current_buttons & ~button_mask
                self.controls.vjoy_dev.update()
                self.status_label.config(text=f"Button {button_id} released (alt method)", foreground="green")
            else:
                self.status_label.config(text="lButtons not available for release", foreground="red")
        except Exception as e:
            self.status_label.config(text=f"Alternative button release error: {str(e)}", foreground="red")
            print(f"Alternative button release error: {str(e)}")

    def test_all_vjoy_functions(self):
        """Test all vJoy functions to verify they're working"""
        if self.controls.vjoy_dev is None:
            self.log_debug("vJoy device not available")
            return
            
        try:
            # Test axes
            self.log_debug("Testing vJoy axes...")
            self.controls.vjoy_dev.data.wAxisX = 16384  # 50%
            self.controls.vjoy_dev.data.wAxisY = 8192   # 25% 
            self.controls.vjoy_dev.data.wAxisZ = 24576  # 75%
            self.controls.vjoy_dev.update()
            self.log_debug("Axes set to: X=50%, Y=25%, Z=75%")
            
            # Test buttons
            self.log_debug("Testing vJoy buttons...")
            for i in range(1, 5):  # Test buttons 1-4
                self.log_debug(f"Pressing button {i}")
                self.controls.vjoy_dev.set_button(i, 1)
                self.controls.vjoy_dev.update()
                time.sleep(0.5)
                
                self.log_debug(f"Releasing button {i}")
                self.controls.vjoy_dev.set_button(i, 0)
                self.controls.vjoy_dev.update()
                time.sleep(0.5)
                
            self.log_debug("vJoy test complete")
        except Exception as e:
            self.log_debug(f"vJoy test error: {str(e)}")
            print(f"vJoy test error: {str(e)}")

    def test_vjoy_direct(self):
        """Test vJoy functionality directly"""
        if not hasattr(self.controls, 'vjoy_dev') or self.controls.vjoy_dev is None:
            self.log_debug("vJoy device not available")
            return
        
        try:
            # Test basic axis functionality
            self.log_debug("Setting X axis to 50%")
            self.controls.vjoy_dev.data.wAxisX = 16384  # 50%
            self.controls.vjoy_dev.update()
            time.sleep(0.5)
            
            self.log_debug("Setting X axis to 100%")
            self.controls.vjoy_dev.data.wAxisX = 32768  # 100%
            self.controls.vjoy_dev.update()
            time.sleep(0.5)
            
            self.log_debug("Setting X axis to 0%")
            self.controls.vjoy_dev.data.wAxisX = 0  # 0%
            self.controls.vjoy_dev.update()
            time.sleep(0.5)
            
            # Test basic button functionality
            self.log_debug("Testing button 1")
            self.controls.vjoy_dev.set_button(1, 1)  # Press
            self.controls.vjoy_dev.update()
            time.sleep(0.5)
            
            self.controls.vjoy_dev.set_button(1, 0)  # Release
            self.controls.vjoy_dev.update()
            
            self.log_debug("vJoy test completed")
        except Exception as e:
            self.log_debug(f"vJoy test error: {str(e)}")

    def reset_vjoy(self):
        """Reset all vJoy controls to default state"""
        if not hasattr(self.controls, 'vjoy_dev') or self.controls.vjoy_dev is None:
            self.log_debug("vJoy device not available")
            return
        
        try:
            # Reset all axes to center
            self.controls.vjoy_dev.data.wAxisX = 0
            self.controls.vjoy_dev.data.wAxisY = 0
            self.controls.vjoy_dev.data.wAxisZ = 0
            self.controls.vjoy_dev.data.wAxisXRot = 0
            self.controls.vjoy_dev.data.wAxisYRot = 0
            self.controls.vjoy_dev.data.wAxisZRot = 0
            self.controls.vjoy_dev.data.wSlider = 0
            self.controls.vjoy_dev.data.wDial = 0
            
            # Reset all buttons (first 32 buttons)
            for i in range(1, 33):
                try:
                    self.controls.vjoy_dev.set_button(i, 0)
                except:
                    pass  # Ignore errors for buttons that don't exist
            
            # Update the device
            self.controls.vjoy_dev.update()
            
            self.log_debug("vJoy reset complete")
        except Exception as e:
            self.log_debug(f"vJoy reset error: {str(e)}")

    def scan_vjoy_buttons(self):
        """Scan for available vJoy buttons"""
        if not hasattr(self.controls, 'vjoy_dev') or self.controls.vjoy_dev is None:
            self.log_debug("vJoy device not available")
            return
        
        self.log_debug("Scanning for available vJoy buttons...")
        
        # Create a new window for the results
        scan_window = tk.Toplevel(self.root)
        scan_window.title("vJoy Button Scanner")
        scan_window.geometry("400x500")
        
        # Create a text widget to display results
        result_text = tk.Text(scan_window, wrap=tk.WORD)
        result_text.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Add a scrollbar
        scrollbar = ttk.Scrollbar(result_text)
        scrollbar.pack(side='right', fill='y')
        result_text.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=result_text.yview)
        
        # Function to add text to the result
        def add_result(text):
            result_text.insert(tk.END, text + "\n")
            result_text.see(tk.END)
            # Update the window to show progress
            scan_window.update()
        
        # Test buttons in a separate thread to keep UI responsive
        def test_buttons():
            try:
                # Get the number of buttons from vJoy
                num_buttons = 32  # Default to testing 32 buttons
                
                add_result(f"Testing up to {num_buttons} buttons...")
                
                # Test each button
                working_buttons = []
                for i in range(1, num_buttons + 1):
                    try:
                        # Try to press and release the button
                        self.controls.vjoy_dev.set_button(i, 1)
                        self.controls.vjoy_dev.update()
                        time.sleep(0.1)
                        
                        self.controls.vjoy_dev.set_button(i, 0)
                        self.controls.vjoy_dev.update()
                        
                        add_result(f"Button {i}: Available")
                        working_buttons.append(i)
                    except Exception as e:
                        add_result(f"Button {i}: Not available ({str(e)})")
                    
                    # Small delay between tests
                    time.sleep(0.1)
                
                # Summary
                if working_buttons:
                    add_result("\nWorking buttons found: " + ", ".join(map(str, working_buttons)))
                else:
                    add_result("\nNo working buttons found!")
                    
                # Add instructions for mapping
                add_result("\nTo map a button to a potentiometer:")
                add_result("1. Go to the Control Panel tab")
                add_result("2. Set a pot's type to 'Button' or 'Switch'")
                add_result("3. Enter one of the working button IDs in the 'Button ID' field")
                add_result("4. Click 'Set' to save the mapping")
                
            except Exception as e:
                add_result(f"Error during button scan: {str(e)}")
        
        # Start the test in a separate thread
        threading.Thread(target=test_buttons, daemon=True).start()
        
        # Add a close button
        ttk.Button(scan_window, text="Close", command=scan_window.destroy).pack(pady=10)

    def test_specific_button(self):
        """Test a specific vJoy button"""
        if not hasattr(self.controls, 'vjoy_dev') or self.controls.vjoy_dev is None:
            self.log_debug("vJoy device not available")
            return
        
        # Ask for button ID
        button_id = simpledialog.askinteger("Test Button", "Enter button ID to test:", 
                                           minvalue=1, maxvalue=128)
        if button_id is None:
            return
        
        try:
            self.log_debug(f"Testing button {button_id}...")
            
            # Press the button
            self.log_debug(f"Pressing button {button_id}")
            self.controls.vjoy_dev.set_button(button_id, 1)
            self.controls.vjoy_dev.update()
            time.sleep(0.5)
            
            # Release the button
            self.log_debug(f"Releasing button {button_id}")
            self.controls.vjoy_dev.set_button(button_id, 0)
            self.controls.vjoy_dev.update()
            
            self.log_debug(f"Button {button_id} test complete")
        except Exception as e:
            self.log_debug(f"Button test error: {str(e)}")

    def test_button_all_methods(self):
        """Test a button using all available methods"""
        if not hasattr(self.controls, 'vjoy_dev') or self.controls.vjoy_dev is None:
            self.log_debug("vJoy device not available")
            return
        
        # Ask for button ID
        button_id = simpledialog.askinteger("Test Button", "Enter button ID to test:", 
                                           minvalue=1, maxvalue=128)
        if button_id is None:
            return
        
        self.log_debug(f"Testing button {button_id} with all available methods...")
        
        # Method 1: Standard set_button method
        try:
            self.log_debug("Method 1: Using set_button method")
            self.controls.vjoy_dev.set_button(button_id, 1)
            self.controls.vjoy_dev.update()
            self.log_debug("Button pressed with Method 1")
            time.sleep(1)
            
            self.controls.vjoy_dev.set_button(button_id, 0)
            self.controls.vjoy_dev.update()
            self.log_debug("Button released with Method 1")
            time.sleep(0.5)
        except Exception as e:
            self.log_debug(f"Method 1 failed: {str(e)}")
        
        # Method 2: Direct bit manipulation
        try:
            self.log_debug("Method 2: Direct bit manipulation")
            
            # Calculate which button array and bit to set
            array_index = (button_id - 1) // 32
            bit_index = (button_id - 1) % 32
            button_mask = 1 << bit_index
            
            self.log_debug(f"Button {button_id} is in array {array_index}, bit {bit_index}, mask {button_mask}")
            
            # Get the current button array
            if array_index == 0 and hasattr(self.controls.vjoy_dev.data, 'lButtons'):
                current_buttons = self.controls.vjoy_dev.data.lButtons
                self.log_debug(f"Current lButtons: {current_buttons}")
                
                # Press button
                self.controls.vjoy_dev.data.lButtons = current_buttons | button_mask
                self.controls.vjoy_dev.update()
                self.log_debug(f"New lButtons: {self.controls.vjoy_dev.data.lButtons}")
                time.sleep(1)
                
                # Release button
                self.controls.vjoy_dev.data.lButtons = current_buttons & ~button_mask
                self.controls.vjoy_dev.update()
                self.log_debug(f"Released lButtons: {self.controls.vjoy_dev.data.lButtons}")
            else:
                self.log_debug(f"Button array {array_index} not available")
        except Exception as e:
            self.log_debug(f"Method 2 failed: {str(e)}")
        
        # Method 3: Try using the pyvjoy API directly
        try:
            self.log_debug("Method 3: Using pyvjoy API directly")
            
            # Inspect the vjoy_dev object
            self.log_debug(f"vJoy device type: {type(self.controls.vjoy_dev)}")
            self.log_debug(f"Available methods: {dir(self.controls.vjoy_dev)}")
            
            # Try to find any button-related methods
            button_methods = [method for method in dir(self.controls.vjoy_dev) if 'button' in method.lower()]
            self.log_debug(f"Button-related methods: {button_methods}")
            
            # Try each method if available
            for method_name in button_methods:
                try:
                    method = getattr(self.controls.vjoy_dev, method_name)
                    if callable(method):
                        self.log_debug(f"Trying method: {method_name}")
                        if method_name == 'set_button':
                            method(button_id, 1)
                            self.controls.vjoy_dev.update()
                            time.sleep(0.5)
                            method(button_id, 0)
                            self.controls.vjoy_dev.update()
                        else:
                            # Try with just the button ID
                            try:
                                method(button_id)
                                self.controls.vjoy_dev.update()
                                time.sleep(0.5)
                            except:
                                # Try with button ID and state
                                try:
                                    method(button_id, 1)
                                    self.controls.vjoy_dev.update()
                                    time.sleep(0.5)
                                    method(button_id, 0)
                                    self.controls.vjoy_dev.update()
                                except:
                                    self.log_debug(f"Could not call {method_name} with standard arguments")
                except Exception as method_error:
                    self.log_debug(f"Method {method_name} failed: {str(method_error)}")
        except Exception as e:
            self.log_debug(f"Method 3 failed: {str(e)}")
        
        self.log_debug("Button test complete")

    def inspect_vjoy_library(self):
        """Inspect the pyvjoy library to understand its capabilities"""
        if not hasattr(self.controls, 'vjoy_dev') or self.controls.vjoy_dev is None:
            self.log_debug("vJoy device not available")
            return
        
        # Create a new window for the results
        inspect_window = tk.Toplevel(self.root)
        inspect_window.title("vJoy Library Inspection")
        inspect_window.geometry("600x500")
        
        # Create a text widget to display results
        result_text = tk.Text(inspect_window, wrap=tk.WORD)
        result_text.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Add a scrollbar
        scrollbar = ttk.Scrollbar(result_text)
        scrollbar.pack(side='right', fill='y')
        result_text.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=result_text.yview)
        
        # Function to add text to the result
        def add_result(text):
            result_text.insert(tk.END, text + "\n")
            result_text.see(tk.END)
        
        try:
            # Get information about the vJoy device
            add_result("vJoy Device Information:")
            add_result(f"Type: {type(self.controls.vjoy_dev)}")
            add_result(f"Module: {self.controls.vjoy_dev.__module__}")
            add_result(f"Dir: {dir(self.controls.vjoy_dev)}")
            
            # Get information about the data structure
            add_result("\nvJoy Data Structure:")
            add_result(f"Type: {type(self.controls.vjoy_dev.data)}")
            add_result(f"Dir: {dir(self.controls.vjoy_dev.data)}")
            
            # Check for button-related attributes and methods
            add_result("\nButton-related attributes and methods:")
            for item in dir(self.controls.vjoy_dev):
                if 'button' in item.lower():
                    add_result(f"- {item}")
            
            # Check for axis-related attributes and methods
            add_result("\nAxis-related attributes and methods:")
            for item in dir(self.controls.vjoy_dev.data):
                if 'axis' in item.lower():
                    add_result(f"- {item}")
            
            # Try to get more information about the set_button method
            if hasattr(self.controls.vjoy_dev, 'set_button'):
                add_result("\nset_button method:")
                add_result(f"Type: {type(self.controls.vjoy_dev.set_button)}")
                add_result(f"Doc: {self.controls.vjoy_dev.set_button.__doc__}")
            
            # Try to get the source code if possible
            try:
                if hasattr(self.controls.vjoy_dev, 'set_button'):
                    source = inspect.getsource(self.controls.vjoy_dev.set_button)
                    add_result("\nset_button source code:")
                    add_result(source)
            except Exception as source_error:
                add_result(f"Could not get source code: {str(source_error)}")
            
        except Exception as e:
            add_result(f"Error during inspection: {str(e)}")
        
        # Add a close button
        ttk.Button(inspect_window, text="Close", command=inspect_window.destroy).pack(pady=10)

    def try_alternative_button_method(self):
        """Try an alternative method for setting vJoy buttons"""
        if not hasattr(self.controls, 'vjoy_dev') or self.controls.vjoy_dev is None:
            self.log_debug("vJoy device not available")
            return
        
        # Ask for button ID
        button_id = simpledialog.askinteger("Test Button", "Enter button ID to test:", 
                                           minvalue=1, maxvalue=128)
        if button_id is None:
            return
        
        self.log_debug(f"Testing button {button_id} with alternative method...")
        
        try:
            # Try to access the underlying vJoy SDK directly
            import ctypes
            
            # Try to find the vJoy DLL
            try:
                vjoy_dll = ctypes.WinDLL("vJoyInterface.dll")
                self.log_debug("Found vJoyInterface.dll")
            except:
                try:
                    # Try to find it in the pyvjoy package
                    import pyvjoy
                    import os
                    pyvjoy_path = os.path.dirname(pyvjoy.__file__)
                    vjoy_dll_path = os.path.join(pyvjoy_path, "vJoyInterface.dll")
                    self.log_debug(f"Looking for DLL at: {vjoy_dll_path}")
                    
                    if os.path.exists(vjoy_dll_path):
                        vjoy_dll = ctypes.WinDLL(vjoy_dll_path)
                        self.log_debug("Found vJoyInterface.dll in pyvjoy package")
                    else:
                        self.log_debug("Could not find vJoyInterface.dll")
                        return
                except Exception as dll_error:
                    self.log_debug(f"Error finding vJoyInterface.dll: {str(dll_error)}")
                    return
            
            # Try to get the SetBtn function
            try:
                set_btn = vjoy_dll.SetBtn
                self.log_debug("Found SetBtn function")
                
                # Set the argument types
                set_btn.argtypes = [ctypes.c_bool, ctypes.c_uint, ctypes.c_uint]
                set_btn.restype = ctypes.c_bool
                
                # Try to press the button
                self.log_debug(f"Pressing button {button_id}")
                result = set_btn(True, 1, button_id)  # True = pressed, 1 = device ID, button_id = button number
                self.log_debug(f"SetBtn result: {result}")
                
            except Exception as btn_error:
                self.log_debug(f"Error using SetBtn: {str(btn_error)}")
        
        except Exception as e:
            self.log_debug(f"Alternative button method failed: {str(e)}")

    def test_direct_button_access(self):
        """Test button using direct memory access to vJoy data structure"""
        if not hasattr(self.controls, 'vjoy_dev') or self.controls.vjoy_dev is None:
            self.log_debug("vJoy device not available")
            return
        
        # Ask for button ID
        button_id = simpledialog.askinteger("Test Button", "Enter button ID to test:", 
                                           minvalue=1, maxvalue=32)
        if button_id is None:
            return
        
        self.log_debug(f"Testing button {button_id} using direct memory access...")
        
        try:
            # Check if lButtons is available
            if not hasattr(self.controls.vjoy_dev.data, 'lButtons'):
                self.log_debug("lButtons not available in vJoy data structure")
                return
            
            # Get current button state
            current_buttons = self.controls.vjoy_dev.data.lButtons
            self.log_debug(f"Current lButtons value: {current_buttons} (hex: {hex(current_buttons)})")
            
            # Calculate which bit to set
            bit_position = button_id - 1
            button_mask = 1 << bit_position
            self.log_debug(f"Button {button_id} corresponds to bit position {bit_position}")
            self.log_debug(f"Button mask: {button_mask} (hex: {hex(button_mask)})")
            
            # Check if button is currently pressed
            is_pressed = (current_buttons & button_mask) != 0
            self.log_debug(f"Button {button_id} is currently {'pressed' if is_pressed else 'released'}")
            
            # Press the button
            self.log_debug(f"Pressing button {button_id}...")
            self.controls.vjoy_dev.data.lButtons = current_buttons | button_mask
            self.controls.vjoy_dev.update()
            
            # Get updated button state
            updated_buttons = self.controls.vjoy_dev.data.lButtons
            self.log_debug(f"Updated lButtons value: {updated_buttons} (hex: {hex(updated_buttons)})")
            
            # Wait a moment
            time.sleep(1)
            
            # Release the button
            self.log_debug(f"Releasing button {button_id}...")
            self.controls.vjoy_dev.data.lButtons = updated_buttons & ~button_mask
            self.controls.vjoy_dev.update()
            
            # Get final button state
            final_buttons = self.controls.vjoy_dev.data.lButtons
            self.log_debug(f"Final lButtons value: {final_buttons} (hex: {hex(final_buttons)})")
            
            self.log_debug(f"Button {button_id} test complete")
        except Exception as e:
            self.log_debug(f"Direct button access error: {str(e)}")

    def check_vjoy_capabilities(self):
        """Check what capabilities are available in the vJoy installation"""
        if not hasattr(self.controls, 'vjoy_dev') or self.controls.vjoy_dev is None:
            self.log_debug("vJoy device not available")
            return
        
        self.log_debug("Checking vJoy capabilities...")
        
        # Check for button-related attributes and methods
        button_capabilities = []
        
        # Check for set_button method
        if hasattr(self.controls.vjoy_dev, 'set_button'):
            button_capabilities.append("set_button method")
        
        # Check for lButtons attribute
        if hasattr(self.controls.vjoy_dev.data, 'lButtons'):
            button_capabilities.append("lButtons attribute")
            self.log_debug(f"lButtons current value: {self.controls.vjoy_dev.data.lButtons}")
        
        # Check for other button arrays
        for attr in ['lButtonsEx1', 'lButtonsEx2', 'lButtonsEx3']:
            if hasattr(self.controls.vjoy_dev.data, attr):
                button_capabilities.append(f"{attr} attribute")
        
        # Report findings
        if button_capabilities:
            self.log_debug(f"Found button capabilities: {', '.join(button_capabilities)}")
        else:
            self.log_debug("No button capabilities found!")
        
        # Check for axis-related attributes
        axis_capabilities = []
        for attr in dir(self.controls.vjoy_dev.data):
            if 'Axis' in attr or attr in ['wSlider', 'wDial']:
                axis_capabilities.append(attr)
        
        if axis_capabilities:
            self.log_debug(f"Found axis capabilities: {', '.join(axis_capabilities)}")
        else:
            self.log_debug("No axis capabilities found!")
        
        # Try to get vJoy version
        try:
            if hasattr(self.controls.vjoy_dev, 'version'):
                self.log_debug(f"vJoy version: {self.controls.vjoy_dev.version}")
            elif hasattr(self.controls.vjoy_dev, 'get_version'):
                self.log_debug(f"vJoy version: {self.controls.vjoy_dev.get_version()}")
        except:
            self.log_debug("Could not determine vJoy version")

    def try_vjoy_ctypes(self):
        """Try to use ctypes to directly access vJoy DLL"""
        self.log_debug("Trying to access vJoy DLL directly using ctypes...")
        
        try:
            import ctypes
            import os
            
            # Try to find the vJoy DLL
            vjoy_dll_paths = [
                "vJoyInterface.dll",  # Current directory
                os.path.join(os.environ.get('PROGRAMFILES', 'C:\\Program Files'), "vJoy", "x64", "vJoyInterface.dll"),
                os.path.join(os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)'), "vJoy", "x86", "vJoyInterface.dll")
            ]
            
            # Try to import pyvjoy to find its location
            try:
                import pyvjoy
                pyvjoy_path = os.path.dirname(pyvjoy.__file__)
                vjoy_dll_paths.append(os.path.join(pyvjoy_path, "vJoyInterface.dll"))
            except:
                self.log_debug("Could not import pyvjoy to find DLL location")
            
            # Try each path
            vjoy_dll = None
            for path in vjoy_dll_paths:
                try:
                    self.log_debug(f"Trying to load DLL from: {path}")
                    if os.path.exists(path):
                        vjoy_dll = ctypes.WinDLL(path)
                        self.log_debug(f"Successfully loaded vJoy DLL from {path}")
                        break
                except Exception as dll_error:
                    self.log_debug(f"Failed to load DLL from {path}: {str(dll_error)}")
            
            if vjoy_dll is None:
                self.log_debug("Could not load vJoy DLL from any location")
                return
            
            # Try to get vJoy version
            try:
                if hasattr(vjoy_dll, 'vJoyEnabled'):
                    enabled_func = vjoy_dll.vJoyEnabled
                    enabled_func.restype = ctypes.c_bool
                    is_enabled = enabled_func()
                    self.log_debug(f"vJoy enabled: {is_enabled}")
                
                if hasattr(vjoy_dll, 'GetvJoyVersion'):
                    version_func = vjoy_dll.GetvJoyVersion
                    version_func.restype = ctypes.c_short
                    version = version_func()
                    self.log_debug(f"vJoy version: {version}")
            except Exception as version_error:
                self.log_debug(f"Error getting vJoy version: {str(version_error)}")
            
            # Try to find button-related functions
            button_functions = []
            for func_name in ['SetBtn', 'GetBtn']:
                if hasattr(vjoy_dll, func_name):
                    button_functions.append(func_name)
            
            if button_functions:
                self.log_debug(f"Found button functions: {', '.join(button_functions)}")
            else:
                self.log_debug("No button functions found in vJoy DLL")
            
            # Try to use SetBtn function if available
            if 'SetBtn' in button_functions:
                try:
                    # Ask for button ID
                    button_id = simpledialog.askinteger("Test Button", "Enter button ID to test:", 
                                                      minvalue=1, maxvalue=32)
                    if button_id is None:
                        return
                    
                    # Get the SetBtn function
                    set_btn = vjoy_dll.SetBtn
                    
                    # Set argument types and return type
                    set_btn.argtypes = [ctypes.c_bool, ctypes.c_uint, ctypes.c_uint]
                    set_btn.restype = ctypes.c_bool
                    
                    # Try to press the button
                    self.log_debug(f"Pressing button {button_id} using SetBtn...")
                    result = set_btn(True, 1, button_id)  # True = pressed, 1 = device ID, button_id = button number
                    self.log_debug(f"SetBtn result: {result}")
                    
                    time.sleep(1)
                    
                    # Release the button
                    self.log_debug(f"Releasing button {button_id} using SetBtn...")
                    result = set_btn(False, 1, button_id)  # False = released
                    self.log_debug(f"SetBtn result: {result}")
                except Exception as btn_error:
                    self.log_debug(f"Error using SetBtn: {str(btn_error)}")
        
        except Exception as e:
            self.log_debug(f"Error accessing vJoy DLL: {str(e)}")

    def test_control_panel_mapping(self):
        """Test control panel mapping directly"""
        if not hasattr(self.controls, 'vjoy_dev') or self.controls.vjoy_dev is None:
            self.log_debug("vJoy device not available")
            return
        
        self.log_debug("Testing control panel mapping...")
        
        # Create a test window
        test_window = tk.Toplevel(self.root)
        test_window.title("Control Panel Mapping Test")
        test_window.geometry("600x400")
        
        # Create a frame for the controls
        controls_frame = ttk.Frame(test_window, padding=10)
        controls_frame.pack(fill='both', expand=True)
        
        # Create sliders for each pot
        sliders = []
        for i in range(7):
            pot_frame = ttk.LabelFrame(controls_frame, text=f"Pot {i+1}: {self.controls.control_panel.pot_config[i]['name']}")
            pot_frame.pack(fill='x', padx=5, pady=5)
            
            # Show current configuration
            config = self.controls.control_panel.pot_config[i]
            config_text = f"Type: {config['type']}"
            if config['type'] == 'Axis' and config['vjoy_axis']:
                config_text += f", Axis: {config['vjoy_axis']}"
            elif (config['type'] == 'Switch' or config['type'] == 'Button') and config['button_id']:
                config_text += f", Button: {config['button_id']}"
            
            ttk.Label(pot_frame, text=config_text).pack(anchor='w')
            
            # Create a slider
            slider_var = tk.IntVar(value=0)
            slider = ttk.Scale(pot_frame, from_=0, to=1023, variable=slider_var, orient='horizontal')
            slider.pack(fill='x', padx=5, pady=5)
            
            # Create a label to show the value
            value_label = ttk.Label(pot_frame, text="0")
            value_label.pack(side='right')
            
            # Update the label when the slider changes
            def update_label(var, label=value_label):
                label.config(text=str(var.get()))
            
            slider_var.trace_add("write", lambda *args, var=slider_var: update_label(var))
            
            # Store the slider and variable
            sliders.append((slider, slider_var))
        
        # Create a button to test the mapping
        def test_mapping():
            # Get the values from the sliders
            values = [var.get() for _, var in sliders]
            
            # Process the values
            self.log_debug(f"Testing with values: {values}")
            processed = self.controls.process_control_panel(values)
            self.log_debug(f"Processed values: {processed}")
            
            # Update the status
            status_label.config(text=f"Tested with values: {values}")
        
        # Create a status label
        status_label = ttk.Label(test_window, text="Ready to test")
        status_label.pack(pady=5)
        
        # Create a button frame
        button_frame = ttk.Frame(test_window)
        button_frame.pack(fill='x', padx=10, pady=10)
        
        # Add test button
        ttk.Button(button_frame, text="Test Mapping", command=test_mapping).pack(side='left', padx=5)
        
        # Add close button
        ttk.Button(button_frame, text="Close", command=test_window.destroy).pack(side='right', padx=5)

    def reset_control_panel_mapping(self):
        """Reset all control panel mappings"""
        for i in range(len(self.controls.control_panel.pot_config)):
            # Reset to default settings
            self.controls.control_panel.pot_config[i]['vjoy_axis'] = None
            self.controls.control_panel.pot_config[i]['button_id'] = None
        
        self.status_label.config(text="Control panel mappings reset", foreground="blue")
        self.root.after(2000, lambda: self.status_label.config(text="Connected", foreground="green"))

    def test_button_bit_manipulation(self):
        """Test button using bit manipulation"""
        if not hasattr(self.controls, 'vjoy_dev') or self.controls.vjoy_dev is None:
            self.log_debug("vJoy device not available")
            return
        
        # Ask for button ID
        button_id = simpledialog.askinteger("Test Button", "Enter button ID to test:", 
                                           minvalue=1, maxvalue=32)
        if button_id is None:
            return
        
        self.log_debug(f"Testing button {button_id} using bit manipulation...")
        
        try:
            # Calculate which bit to set
            bit_position = button_id - 1
            button_mask = 1 << bit_position
            
            # Get current button state
            current_buttons = self.controls.vjoy_dev.data.lButtons
            self.log_debug(f"Current lButtons: {current_buttons} (hex: {hex(current_buttons)})")
            
            # Press the button
            self.log_debug(f"Pressing button {button_id}...")
            self.controls.vjoy_dev.data.lButtons = current_buttons | button_mask
            self.controls.vjoy_dev.update()
            
            # Get updated button state
            updated_buttons = self.controls.vjoy_dev.data.lButtons
            self.log_debug(f"Updated lButtons: {updated_buttons} (hex: {hex(updated_buttons)})")
            
            # Wait a moment
            time.sleep(1)
            
            # Release the button
            self.log_debug(f"Releasing button {button_id}...")
            self.controls.vjoy_dev.data.lButtons = updated_buttons & ~button_mask
            self.controls.vjoy_dev.update()
            
            # Get final button state
            final_buttons = self.controls.vjoy_dev.data.lButtons
            self.log_debug(f"Final lButtons: {final_buttons} (hex: {hex(final_buttons)})")
            
            self.log_debug(f"Button {button_id} test complete")
        except Exception as e:
            self.log_debug(f"Button bit manipulation error: {str(e)}")

    def check_lbuttons_availability(self):
        """Check if lButtons attribute is available"""
        if not hasattr(self.controls, 'vjoy_dev') or self.controls.vjoy_dev is None:
            self.log_debug("vJoy device not available")
            return
        
        self.log_debug("Checking lButtons availability...")
        
        try:
            # Check if lButtons is available
            if hasattr(self.controls.vjoy_dev.data, 'lButtons'):
                current_buttons = self.controls.vjoy_dev.data.lButtons
                self.log_debug(f"lButtons is available. Current value: {current_buttons} (hex: {hex(current_buttons)})")
                
                # Try to modify lButtons
                self.log_debug("Trying to modify lButtons...")
                original_value = current_buttons
                
                # Set all buttons to 0
                self.controls.vjoy_dev.data.lButtons = 0
                self.controls.vjoy_dev.update()
                self.log_debug(f"Set lButtons to 0. New value: {self.controls.vjoy_dev.data.lButtons}")
                
                # Set all buttons to 1
                self.controls.vjoy_dev.data.lButtons = 0xFFFFFFFF
                self.controls.vjoy_dev.update()
                self.log_debug(f"Set lButtons to 0xFFFFFFFF. New value: {self.controls.vjoy_dev.data.lButtons}")
                
                # Restore original value
                self.controls.vjoy_dev.data.lButtons = original_value
                self.controls.vjoy_dev.update()
                self.log_debug(f"Restored lButtons to original value: {self.controls.vjoy_dev.data.lButtons}")
                
                self.log_debug("lButtons is available and can be modified")
            else:
                self.log_debug("lButtons is NOT available in vJoy data structure")
                
                # Check what button-related attributes are available
                button_attrs = [attr for attr in dir(self.controls.vjoy_dev.data) if 'button' in attr.lower()]
                if button_attrs:
                    self.log_debug(f"Button-related attributes found: {button_attrs}")
                else:
                    self.log_debug("No button-related attributes found in vJoy data structure")
        except Exception as e:
            self.log_debug(f"Error checking lButtons: {str(e)}")

    def reset_toggle_states(self):
        """Reset all toggle states"""
        if hasattr(self.controls, 'button_states'):
            self.controls.button_states = {}
        
        if hasattr(self.controls, 'last_pot_values'):
            self.controls.last_pot_values = {}
        
        self.status_label.config(text="Toggle states reset", foreground="blue")
        self.root.after(2000, lambda: self.status_label.config(text="Connected", foreground="green"))

    def test_toggle_functionality(self):
        """Test toggle functionality"""
        if not hasattr(self.controls, 'vjoy_dev') or self.controls.vjoy_dev is None:
            self.log_debug("vJoy device not available")
            return
        
        # Create a test window
        test_window = tk.Toplevel(self.root)
        test_window.title("Toggle Functionality Test")
        test_window.geometry("400x300")
        
        # Create a frame for the controls
        controls_frame = ttk.Frame(test_window, padding=10)
        controls_frame.pack(fill='both', expand=True)
        
        # Ask for button ID
        button_id_frame = ttk.Frame(controls_frame)
        button_id_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(button_id_frame, text="Button ID:").pack(side='left')
        button_id_var = tk.IntVar(value=1)
        ttk.Spinbox(button_id_frame, from_=1, to=32, textvariable=button_id_var, width=5).pack(side='left', padx=5)
        
        # Create a slider for the pot value
        slider_frame = ttk.Frame(controls_frame)
        slider_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(slider_frame, text="Pot Value:").pack(side='left')
        pot_value_var = tk.IntVar(value=0)
        pot_slider = ttk.Scale(slider_frame, from_=0, to=100, variable=pot_value_var, orient='horizontal')
        pot_slider.pack(side='left', padx=5, fill='x', expand=True)
        
        pot_value_label = ttk.Label(slider_frame, text="0")
        pot_value_label.pack(side='right')
        
        # Update the label when the slider changes
        pot_value_var.trace_add("write", lambda *args: pot_value_label.config(text=str(pot_value_var.get())))
        
        # Create a threshold slider
        threshold_frame = ttk.Frame(controls_frame)
        threshold_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(threshold_frame, text="Threshold:").pack(side='left')
        threshold_var = tk.IntVar(value=50)
        threshold_slider = ttk.Scale(threshold_frame, from_=0, to=100, variable=threshold_var, orient='horizontal')
        threshold_slider.pack(side='left', padx=5, fill='x', expand=True)
        
        threshold_label = ttk.Label(threshold_frame, text="50")
        threshold_label.pack(side='right')
        
        # Update the label when the slider changes
        threshold_var.trace_add("write", lambda *args: threshold_label.config(text=str(threshold_var.get())))
        
        # Create a toggle state display
        toggle_frame = ttk.Frame(controls_frame)
        toggle_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(toggle_frame, text="Toggle State:").pack(side='left')
        toggle_state_var = tk.StringVar(value="OFF")
        toggle_state_label = ttk.Label(toggle_frame, textvariable=toggle_state_var, foreground="red")
        toggle_state_label.pack(side='left', padx=5)
        
        # Create a button to test the toggle
        def test_toggle():
            button_id = button_id_var.get()
            pot_value = pot_value_var.get()
            threshold = threshold_var.get()
            
            # Create a unique key for this button
            button_key = f"test_toggle_button_{button_id}"
            
            # Get the current threshold state
            current_threshold_state = pot_value > threshold
            
            # Get the previous threshold state
            if not hasattr(test_window, 'last_threshold_state'):
                test_window.last_threshold_state = False
            
            # Get the current button state
            if not hasattr(test_window, 'button_state'):
                test_window.button_state = 0
            
            # Toggle the button state when crossing the threshold
            if current_threshold_state != test_window.last_threshold_state:
                if current_threshold_state:  # Only toggle when crossing from below to above threshold
                    # Toggle the button state
                    test_window.button_state = 1 if test_window.button_state == 0 else 0
                    
                    # Update the toggle state display
                    toggle_state_var.set("ON" if test_window.button_state == 1 else "OFF")
                    toggle_state_label.config(foreground="green" if test_window.button_state == 1 else "red")
                    
                    # Try to set the button using direct bit manipulation
                    try:
                        # Calculate which bit to set
                        bit_position = button_id - 1
                        button_mask = 1 << bit_position
                        
                        # Get current button state
                        current_buttons = self.controls.vjoy_dev.data.lButtons
                        
                        # Set or clear the button bit
                        if test_window.button_state:
                            self.controls.vjoy_dev.data.lButtons = current_buttons | button_mask
                        else:
                            self.controls.vjoy_dev.data.lButtons = current_buttons & ~button_mask
                            
                        self.controls.vjoy_dev.update()
                        
                        status_var.set(f"Button {button_id} toggled to {test_window.button_state}")
                    except Exception as e:
                        status_var.set(f"Error: {str(e)}")
            
            # Store the current threshold state
            test_window.last_threshold_state = current_threshold_state
        
        # Create a button to test the toggle
        ttk.Button(controls_frame, text="Test Toggle", command=test_toggle).pack(pady=10)
        
        # Create a status display
        status_var = tk.StringVar(value="Ready to test")
        status_label = ttk.Label(controls_frame, textvariable=status_var)
        status_label.pack(pady=5)
        
        # Create a button to continuously test
        def continuous_test():
            test_toggle()
            if hasattr(test_window, 'continuous_test_id'):
                test_window.after_cancel(test_window.continuous_test_id)
            test_window.continuous_test_id = test_window.after(100, continuous_test)
        
        # Create a button to start/stop continuous testing
        continuous_var = tk.BooleanVar(value=False)
        
        def toggle_continuous():
            if continuous_var.get():
                continuous_test()
                continuous_button.config(text="Stop Continuous Test")
            else:
                if hasattr(test_window, 'continuous_test_id'):
                    test_window.after_cancel(test_window.continuous_test_id)
                continuous_button.config(text="Start Continuous Test")
        
        continuous_button = ttk.Checkbutton(
            controls_frame, 
            text="Start Continuous Test", 
            variable=continuous_var,
            command=toggle_continuous
        )
        continuous_button.pack(pady=5)

    def create_binding_helper(self):
        """Create a helper window for binding buttons to simulator functions"""
        binding_window = tk.Toplevel(self.root)
        binding_window.title("Button Binding Helper")
        binding_window.geometry("500x400")
        
        # Create a frame for the controls
        controls_frame = ttk.Frame(binding_window, padding=10)
        controls_frame.pack(fill='both', expand=True)
        
        # Add instructions
        instructions = """Button Binding Instructions:

1. Select the button ID you want to bind
2. Click "Start Binding Mode"
3. In your simulator, start the control binding process
4. When the simulator is scanning for input, click "Press Button"
5. Hold the button until the simulator recognizes it
6. Click "Release Button" when done

Note: If binding fails, try the "Long Press" option which holds the button longer."""
        
        instruction_label = ttk.Label(controls_frame, text=instructions, justify='left')
        instruction_label.pack(fill='x', padx=5, pady=10)
        
        # Button ID selection
        button_frame = ttk.Frame(controls_frame)
        button_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(button_frame, text="Button ID:").pack(side='left')
        button_id_var = tk.IntVar(value=1)
        ttk.Spinbox(button_frame, from_=1, to=32, textvariable=button_id_var, width=5).pack(side='left', padx=5)
        
        # Long press option
        long_press_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(button_frame, text="Long Press (3 seconds)", variable=long_press_var).pack(side='right', padx=5)
        
        # Status display
        status_var = tk.StringVar(value="Ready")
        status_label = ttk.Label(controls_frame, textvariable=status_var, font=('Arial', 12, 'bold'))
        status_label.pack(pady=10)
        
        # Button state display
        state_frame = ttk.Frame(controls_frame)
        state_frame.pack(fill='x', padx=5, pady=5)
        
        state_label = ttk.Label(state_frame, text="Button State:", font=('Arial', 10))
        state_label.pack(side='left')
        
        button_state_var = tk.StringVar(value="RELEASED")
        button_state_label = ttk.Label(state_frame, textvariable=button_state_var, 
                                      foreground="red", font=('Arial', 10, 'bold'))
        button_state_label.pack(side='left', padx=5)
        
        # Function to press the button
        def press_button():
            button_id = button_id_var.get()
            status_var.set(f"Pressing button {button_id}...")
            button_state_var.set("PRESSED")
            button_state_label.config(foreground="green")
            
            try:
                # Try direct bit manipulation first
                try:
                    # Calculate which bit to set
                    bit_position = button_id - 1
                    button_mask = 1 << bit_position
                    
                    # Get current button state
                    current_buttons = self.controls.vjoy_dev.data.lButtons
                    
                    # Set the button bit
                    self.controls.vjoy_dev.data.lButtons = current_buttons | button_mask
                    self.controls.vjoy_dev.update()
                    
                    print(f"Button {button_id} pressed using bit manipulation")
                except Exception as bit_error:
                    print(f"Bit manipulation failed: {str(bit_error)}")
                    
                    # Try standard method as fallback
                    try:
                        self.controls.vjoy_dev.set_button(button_id, 1)
                        self.controls.vjoy_dev.update()
                        print(f"Button {button_id} pressed using standard method")
                    except Exception as std_error:
                        status_var.set(f"Error: {str(std_error)}")
                        return
                
                # If long press is selected, automatically release after 3 seconds
                if long_press_var.get():
                    binding_window.after(3000, release_button)
                    status_var.set(f"Button {button_id} pressed (will auto-release in 3 seconds)")
                else:
                    status_var.set(f"Button {button_id} pressed - click 'Release Button' when done")
            except Exception as e:
                status_var.set(f"Error: {str(e)}")
        
        # Function to release the button
        def release_button():
            button_id = button_id_var.get()
            status_var.set(f"Releasing button {button_id}...")
            button_state_var.set("RELEASED")
            button_state_label.config(foreground="red")
            
            try:
                # Try direct bit manipulation first
                try:
                    # Calculate which bit to clear
                    bit_position = button_id - 1
                    button_mask = 1 << bit_position
                    
                    # Get current button state
                    current_buttons = self.controls.vjoy_dev.data.lButtons
                    
                    # Clear the button bit
                    self.controls.vjoy_dev.data.lButtons = current_buttons & ~button_mask
                    self.controls.vjoy_dev.update()
                    
                    print(f"Button {button_id} released using bit manipulation")
                except Exception as bit_error:
                    print(f"Bit manipulation failed: {str(bit_error)}")
                    
                    # Try standard method as fallback
                    try:
                        self.controls.vjoy_dev.set_button(button_id, 0)
                        self.controls.vjoy_dev.update()
                        print(f"Button {button_id} released using standard method")
                    except Exception as std_error:
                        status_var.set(f"Error: {str(std_error)}")
                        return
                
                status_var.set(f"Button {button_id} released")
            except Exception as e:
                status_var.set(f"Error: {str(e)}")
        
        # Function to start binding mode
        def start_binding_mode():
            button_id = button_id_var.get()
            status_var.set(f"Binding mode started for button {button_id}")
            
            # Disable the start button and enable the press/release buttons
            start_button.config(state='disabled')
            press_button_btn.config(state='normal')
            release_button_btn.config(state='normal')
            stop_button.config(state='normal')
        
        # Function to stop binding mode
        def stop_binding_mode():
            status_var.set("Binding mode stopped")
            
            # Make sure the button is released
            release_button()
            
            # Enable the start button and disable the press/release buttons
            start_button.config(state='normal')
            press_button_btn.config(state='disabled')
            release_button_btn.config(state='disabled')
            stop_button.config(state='disabled')
        
        # Create buttons
        button_control_frame = ttk.Frame(controls_frame)
        button_control_frame.pack(fill='x', padx=5, pady=10)
        
        start_button = ttk.Button(button_control_frame, text="Start Binding Mode", command=start_binding_mode)
        start_button.pack(side='left', padx=5)
        
        stop_button = ttk.Button(button_control_frame, text="Stop Binding Mode", command=stop_binding_mode, state='disabled')
        stop_button.pack(side='left', padx=5)
        
        press_button_btn = ttk.Button(button_control_frame, text="Press Button", command=press_button, state='disabled')
        press_button_btn.pack(side='left', padx=5)
        
        release_button_btn = ttk.Button(button_control_frame, text="Release Button", command=release_button, state='disabled')
        release_button_btn.pack(side='left', padx=5)
        
        # Add a rapid toggle mode for testing
        toggle_frame = ttk.Frame(controls_frame)
        toggle_frame.pack(fill='x', padx=5, pady=10)
        
        ttk.Label(toggle_frame, text="Rapid Toggle Mode:").pack(side='left')
        
        # Function to rapidly toggle the button
        def rapid_toggle():
            button_id = button_id_var.get()
            
            # Toggle the button state
            if not hasattr(binding_window, 'toggle_state'):
                binding_window.toggle_state = False
            
            binding_window.toggle_state = not binding_window.toggle_state
            
            if binding_window.toggle_state:
                press_button()
            else:
                release_button()
            
            # Schedule the next toggle if rapid toggle is active
            if hasattr(binding_window, 'rapid_toggle_active') and binding_window.rapid_toggle_active:
                binding_window.after(200, rapid_toggle)  # Toggle every 200ms
        
        # Function to start/stop rapid toggle
        def toggle_rapid_toggle():
            if not hasattr(binding_window, 'rapid_toggle_active'):
                binding_window.rapid_toggle_active = False
            
            binding_window.rapid_toggle_active = not binding_window.rapid_toggle_active
            
            if binding_window.rapid_toggle_active:
                rapid_toggle_btn.config(text="Stop Rapid Toggle")
                rapid_toggle()
            else:
                rapid_toggle_btn.config(text="Start Rapid Toggle")
                # Make sure button is released
                release_button()
        
        rapid_toggle_btn = ttk.Button(toggle_frame, text="Start Rapid Toggle", command=toggle_rapid_toggle)
        rapid_toggle_btn.pack(side='left', padx=5)
        
        # When window is closed, make sure to release any pressed buttons
        binding_window.protocol('WM_DELETE_WINDOW', lambda: [release_button(), binding_window.destroy()])

    def test_all_buttons_sequentially(self):
        """Test all buttons sequentially"""
        if not hasattr(self.controls, 'vjoy_dev') or self.controls.vjoy_dev is None:
            self.log_debug("vJoy device not available")
            return
        
        # Create a test window
        test_window = tk.Toplevel(self.root)
        test_window.title("Sequential Button Test")
        test_window.geometry("400x300")
        
        # Create a frame for the controls
        controls_frame = ttk.Frame(test_window, padding=10)
        controls_frame.pack(fill='both', expand=True)
        
        # Add instructions
        instructions = """This will test all buttons sequentially.
Each button will be pressed for 1 second, then released.
Watch your simulator to see which buttons are detected."""
        
        instruction_label = ttk.Label(controls_frame, text=instructions, justify='left')
        instruction_label.pack(fill='x', padx=5, pady=10)
        
        # Button range selection
        range_frame = ttk.Frame(controls_frame)
        range_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(range_frame, text="Start Button:").pack(side='left')
        start_button_var = tk.IntVar(value=1)
        ttk.Spinbox(range_frame, from_=1, to=32, textvariable=start_button_var, width=5).pack(side='left', padx=5)
        
        ttk.Label(range_frame, text="End Button:").pack(side='left')
        end_button_var = tk.IntVar(value=16)
        ttk.Spinbox(range_frame, from_=1, to=32, textvariable=end_button_var, width=5).pack(side='left', padx=5)
        
        # Status display
        status_var = tk.StringVar(value="Ready")
        status_label = ttk.Label(controls_frame, textvariable=status_var, font=('Arial', 12, 'bold'))
        status_label.pack(pady=10)
        
        # Current button display
        current_button_var = tk.StringVar(value="None")
        current_button_label = ttk.Label(controls_frame, textvariable=current_button_var, font=('Arial', 14, 'bold'))
        current_button_label.pack(pady=10)
        
        # Function to test buttons sequentially
        def test_buttons():
            start_button = start_button_var.get()
            end_button = end_button_var.get()
            
            if start_button > end_button:
                status_var.set("Error: Start button must be less than or equal to end button")
                return
            
            status_var.set(f"Testing buttons {start_button} to {end_button}")
            
            # Disable the start button
            start_button_btn.config(state='disabled')
            stop_button_btn.config(state='normal')
            
            # Store the test state in the window
            test_window.testing = True
            test_window.current_button = start_button
            
            # Start testing the first button
            test_next_button()
        
        # Function to test the next button
        def test_next_button():
            if not hasattr(test_window, 'testing') or not test_window.testing:
                return
            
            end_button = end_button_var.get()
            
            if test_window.current_button > end_button:
                # All buttons tested
                status_var.set("Testing complete")
                current_button_var.set("None")
                
                # Enable the start button
                start_button_btn.config(state='normal')
                stop_button_btn.config(state='disabled')
                
                test_window.testing = False
                return
            
            # Update the current button display
            current_button_var.set(f"Button {test_window.current_button}")
            
            # Press the button
            try:
                # Try direct bit manipulation first
                try:
                    # Calculate which bit to set
                    bit_position = test_window.current_button - 1
                    button_mask = 1 << bit_position
                    
                    # Get current button state
                    current_buttons = self.controls.vjoy_dev.data.lButtons
                    
                    # Set the button bit
                    self.controls.vjoy_dev.data.lButtons = current_buttons | button_mask
                    self.controls.vjoy_dev.update()
                    
                    print(f"Button {test_window.current_button} pressed using bit manipulation")
                except Exception as bit_error:
                    print(f"Bit manipulation failed: {str(bit_error)}")
                    
                    # Try standard method as fallback
                    try:
                        self.controls.vjoy_dev.set_button(test_window.current_button, 1)
                        self.controls.vjoy_dev.update()
                        print(f"Button {test_window.current_button} pressed using standard method")
                    except Exception as std_error:
                        status_var.set(f"Error: {str(std_error)}")
                        return
                
                # Schedule to release the button after 1 second
                test_window.after(1000, release_current_button)
            except Exception as e:
                status_var.set(f"Error: {str(e)}")
        
        # Function to release the current button
        def release_current_button():
            if not hasattr(test_window, 'testing') or not test_window.testing:
                return
            
            try:
                # Try direct bit manipulation first
                try:
                    # Calculate which bit to clear
                    bit_position = test_window.current_button - 1
                    button_mask = 1 << bit_position
                    
                    # Get current button state
                    current_buttons = self.controls.vjoy_dev.data.lButtons
                    
                    # Clear the button bit
                    self.controls.vjoy_dev.data.lButtons = current_buttons & ~button_mask
                    self.controls.vjoy_dev.update()
                    
                    print(f"Button {test_window.current_button} released using bit manipulation")
                except Exception as bit_error:
                    print(f"Bit manipulation failed: {str(bit_error)}")
                    
                    # Try standard method as fallback
                    try:
                        self.controls.vjoy_dev.set_button(test_window.current_button, 0)
                        self.controls.vjoy_dev.update()
                        print(f"Button {test_window.current_button} released using standard method")
                    except Exception as std_error:
                        status_var.set(f"Error: {str(std_error)}")
                        return
                
                # Move to the next button
                test_window.current_button += 1
                
                # Schedule to test the next button after a short delay
                test_window.after(500, test_next_button)
            except Exception as e:
                status_var.set(f"Error: {str(e)}")
        
        # Function to stop testing
        def stop_testing():
            if hasattr(test_window, 'testing'):
                test_window.testing = False
            
            # Release the current button if any
            if hasattr(test_window, 'current_button'):
                try:
                    # Try direct bit manipulation first
                    try:
                        # Calculate which bit to clear
                        bit_position = test_window.current_button - 1
                        button_mask = 1 << bit_position
                        
                        # Get current button state
                        current_buttons = self.controls.vjoy_dev.data.lButtons
                        
                        # Clear the button bit
                        self.controls.vjoy_dev.data.lButtons = current_buttons & ~button_mask
                        self.controls.vjoy_dev.update()
                    except Exception:
                        # Try standard method as fallback
                        try:
                            self.controls.vjoy_dev.set_button(test_window.current_button, 0)
                            self.controls.vjoy_dev.update()
                        except Exception:
                            pass
                except Exception:
                    pass
            
            status_var.set("Testing stopped")
            current_button_var.set("None")
            
            # Enable the start button
            start_button_btn.config(state='normal')
            stop_button_btn.config(state='disabled')
        
        # Create buttons
        button_control_frame = ttk.Frame(controls_frame)
        button_control_frame.pack(fill='x', padx=5, pady=10)
        
        start_button_btn = ttk.Button(button_control_frame, text="Start Testing", command=test_buttons)
        start_button_btn.pack(side='left', padx=5)
        
        stop_button_btn = ttk.Button(button_control_frame, text="Stop Testing", command=stop_testing, state='disabled')
        stop_button_btn.pack(side='left', padx=5)
        
        # When window is closed, make sure to stop testing
        test_window.protocol('WM_DELETE_WINDOW', lambda: [stop_testing(), test_window.destroy()])

    def reset_button_states(self):
        """Reset all button states"""
        try:
            # Reset button states
            self.controls.button_states = {}
            
            # Reset last pot values
            if hasattr(self.controls, 'last_pot_values'):
                self.controls.last_pot_values = {}
            
            # Save settings
            self.save_settings()
            
            self.log_debug("Button states reset")
        except Exception as e:
            self.log_debug(f"Error resetting button states: {str(e)}")

    def create_control_panel_ui(self, parent):
        """Create UI for control panel configuration"""
        # Clear existing pot frames
        self.pot_frames = []
        
        # Initialize control panel variables if they don't exist
        if not hasattr(self, 'control_panel_baud_rate'):
            self.control_panel_baud_rate = 115200
        
        if not hasattr(self, 'pot_name_vars'):
            self.pot_name_vars = []
        
        if not hasattr(self, 'pot_type_vars'):
            self.pot_type_vars = []
        
        if not hasattr(self, 'pot_inversion_vars'):
            self.pot_inversion_vars = []
        
        if not hasattr(self, 'pot_threshold_vars'):
            self.pot_threshold_vars = []
        
        if not hasattr(self, 'pot_axis_vars'):
            self.pot_axis_vars = []
        
        if not hasattr(self, 'pot_button_vars'):
            self.pot_button_vars = []
        
        # Create a frame for the potentiometers
        pots_frame = ttk.LabelFrame(parent, text="Potentiometers", padding=10)
        pots_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Create UI for each potentiometer
        for i in range(7):
            pot_frame = ttk.LabelFrame(pots_frame, text=f"Potentiometer {i+1}", padding=5)
            pot_frame.grid(row=i//3, column=i%3, padx=5, pady=5, sticky='ew')
            
            # Name entry
            name_frame = ttk.Frame(pot_frame)
            name_frame.pack(fill='x', pady=2)
            ttk.Label(name_frame, text="Name:").pack(side='left')
            
            name_var = tk.StringVar(value=self.controls.control_panel.pot_config[i]['name'])
            name_entry = ttk.Entry(name_frame, textvariable=name_var, width=15)
            name_entry.pack(side='left', padx=5, fill='x', expand=True)
            self.pot_name_vars.append(name_var)
            
            # Save button for name
            ttk.Button(name_frame, text="Set", 
                      command=lambda idx=i, var=name_var: self.set_pot_name(idx, var.get())).pack(side='right')
            
            # Type selection
            type_frame = ttk.Frame(pot_frame)
            type_frame.pack(fill='x', pady=2)
            ttk.Label(type_frame, text="Type:").pack(side='left')
            
            type_var = tk.StringVar(value=self.controls.control_panel.pot_config[i]['type'])
            type_combo = ttk.Combobox(type_frame, textvariable=type_var, 
                                     values=self.controls.control_panel.CONTROL_TYPES, width=10)
            type_combo.pack(side='left', padx=5)
            self.pot_type_vars.append(type_var)
            type_combo.bind("<<ComboboxSelected>>", 
                           lambda e, idx=i, var=type_var: self.set_pot_type(idx, var.get()))
            
            # Inversion checkbox
            invert_var = tk.BooleanVar(value=self.controls.control_panel.pot_config[i]['invert'])
            invert_check = ttk.Checkbutton(type_frame, text="Invert", variable=invert_var,
                                         command=lambda idx=i: self.toggle_pot_inversion(idx))
            invert_check.pack(side='right')
            self.pot_inversion_vars.append(invert_var)
            
            # Threshold for switch/button mode
            threshold_frame = ttk.Frame(pot_frame)
            threshold_frame.pack(fill='x', pady=2)
            ttk.Label(threshold_frame, text="Threshold:").pack(side='left')
            
            threshold_var = tk.IntVar(value=self.controls.control_panel.pot_config[i]['threshold'])
            threshold_scale = ttk.Scale(threshold_frame, from_=0, to=100, variable=threshold_var,
                                      orient='horizontal', length=100)
            threshold_scale.pack(side='left', padx=5, fill='x', expand=True)
            self.pot_threshold_vars.append(threshold_var)
            threshold_scale.bind("<ButtonRelease-1>", 
                               lambda e, idx=i, var=threshold_var: self.set_pot_threshold(idx, var.get()))
            
            threshold_label = ttk.Label(threshold_frame, text="50%", width=5)
            threshold_label.pack(side='right')
            threshold_var.trace_add("write", lambda *args, label=threshold_label, var=threshold_var: 
                                  label.config(text=f"{var.get()}%"))
            
            # Add vJoy mapping UI
            vjoy_frame = ttk.Frame(pot_frame)
            vjoy_frame.pack(fill='x', pady=2)
            ttk.Label(vjoy_frame, text="vJoy:").pack(side='left')
            
            # Create a list of available vJoy axes
            vjoy_axes = ["None", "X", "Y", "Z", "RX", "RY", "RZ", "SL0", "SL1"]
            
            # Get current vjoy_axis value or "None" if not set
            current_axis = self.controls.control_panel.pot_config[i]['vjoy_axis'] or "None"
            
            axis_var = tk.StringVar(value=current_axis)
            vjoy_combo = ttk.Combobox(vjoy_frame, textvariable=axis_var, 
                                     values=vjoy_axes, width=8)
            vjoy_combo.pack(side='left', padx=5)
            self.pot_axis_vars.append(axis_var)
            vjoy_combo.bind("<<ComboboxSelected>>", 
                           lambda e, idx=i, var=axis_var: self.set_pot_vjoy_axis(idx, var.get()))
            
            # Button ID for button/switch mode
            button_frame = ttk.Frame(pot_frame)
            button_frame.pack(fill='x', pady=2)
            ttk.Label(button_frame, text="Button ID:").pack(side='left')
            
            # Get current button_id value or empty if not set
            current_button = self.controls.control_panel.pot_config[i]['button_id'] or ""
            
            button_var = tk.StringVar(value=str(current_button))
            button_entry = ttk.Entry(button_frame, textvariable=button_var, width=5)
            button_entry.pack(side='left', padx=5)
            self.pot_button_vars.append(button_var)
            
            # Save button for button ID
            ttk.Button(button_frame, text="Set", 
                      command=lambda idx=i, var=button_var: self.set_pot_button_id(idx, var.get())).pack(side='left', padx=5)
            
            # Add a test button for button/switch mode
            ttk.Button(button_frame, text="Test", 
                      command=lambda idx=i: self.test_vjoy_button(idx)).pack(side='right', padx=5)
            
            # Calibration buttons
            cal_frame = ttk.Frame(pot_frame)
            cal_frame.pack(fill='x', pady=2)
            ttk.Button(cal_frame, text="Set Min", 
                      command=lambda idx=i: self.calibrate_pot_min(idx)).pack(side='left', padx=2)
            ttk.Button(cal_frame, text="Set Max", 
                      command=lambda idx=i: self.calibrate_pot_max(idx)).pack(side='left', padx=2)
            
            # Value display
            value_frame = ttk.Frame(pot_frame)
            value_frame.pack(fill='x', pady=2)
            ttk.Label(value_frame, text="Value:").pack(side='left')
            
            # Progress bar for value
            value_bar = ttk.Progressbar(value_frame, length=100, mode='determinate')
            value_bar.pack(side='left', padx=5, fill='x', expand=True)
            
            value_label = ttk.Label(value_frame, text="0%", width=5)
            value_label.pack(side='right')
            
            # Add raw value display
            raw_frame = ttk.Frame(pot_frame)
            raw_frame.pack(fill='x', pady=2)
            raw_label = ttk.Label(raw_frame, text="Raw: 0", width=15)
            raw_label.pack(side='left')
            
            # Add calibration values display
            cal_values_frame = ttk.Frame(pot_frame)
            cal_values_frame.pack(fill='x', pady=2)
            cal_min_label = ttk.Label(cal_values_frame, text=f"Min: {self.controls.control_panel.pot_config[i]['calibrated_min']}")
            cal_min_label.pack(side='left', padx=5)
            cal_max_label = ttk.Label(cal_values_frame, text=f"Max: {self.controls.control_panel.pot_config[i]['calibrated_max']}")
            cal_max_label.pack(side='right', padx=5)
            
            # Store references to UI elements
            frame_data = {
                'frame': pot_frame,
                'value_bar': value_bar,
                'value_label': value_label,
                'raw_label': raw_label,
                'cal_min_label': cal_min_label,
                'cal_max_label': cal_max_label
            }
            self.pot_frames.append(frame_data)
        
        # Add utility buttons at the bottom
        button_frame = ttk.Frame(parent)
        button_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(button_frame, text="Scan vJoy Buttons", 
                  command=self.scan_vjoy_buttons).pack(side='left', padx=5)
        
        ttk.Button(button_frame, text="Reset All Mappings", 
                  command=self.reset_control_panel_mapping).pack(side='right', padx=5)
        
        ttk.Button(button_frame, text="Reset Toggle States", 
                  command=self.reset_toggle_states).pack(side='right', padx=5)
        
        ttk.Button(button_frame, text="Button Binding Helper", 
                  command=self.create_binding_helper).pack(side='left', padx=5)
        
        ttk.Button(button_frame, text="Save Settings", 
                  command=self.save_settings).pack(side='left', padx=5)

if __name__ == "__main__":
    app = FlightControlGUI()
    app.run() 