#include <Arduino.h>

// Pin definitions for joystick
const int PIN_X = 1;  // ADC1_CH0 - X axis
const int PIN_Y = 2;  // ADC1_CH1 - Y axis
const int PIN_SW = 5; // Digital pin for switch/button

// ADC resolution
const int ADC_RESOLUTION = 12; // ESP32 has 12-bit ADC (0-4095)
const int SAMPLE_COUNT = 5;    // Reduced from 10
const int LOOP_DELAY = 5;       // Reduced from 10

// Add moving average arrays
int x_samples[SAMPLE_COUNT];
int y_samples[SAMPLE_COUNT];
int sample_index = 0;

// Variables for switch debouncing
bool lastSwitchState = HIGH;
unsigned long lastDebounceTime = 0;
const unsigned long DEBOUNCE_DELAY = 50;

void setup() {
  // Initialize serial communication
  Serial.begin(115200);
  
  // Configure ADC resolution
  analogReadResolution(ADC_RESOLUTION);
  
  // Configure pins
  pinMode(PIN_X, INPUT);
  pinMode(PIN_Y, INPUT);
  pinMode(PIN_SW, INPUT_PULLUP);
  
  // Initialize sample arrays
  for (int i = 0; i < SAMPLE_COUNT; i++) {
    x_samples[i] = 0;
    y_samples[i] = 0;
  }
}

void loop() {
    // Read raw values
    int x_raw = analogRead(PIN_X);
    int y_raw = analogRead(PIN_Y);
    
    // Update moving averages
    x_samples[sample_index] = x_raw;
    y_samples[sample_index] = y_raw;
    sample_index = (sample_index + 1) % SAMPLE_COUNT;
    
    // Calculate averages
    long x_sum = 0, y_sum = 0;
    for(int i = 0; i < SAMPLE_COUNT; i++) {
        x_sum += x_samples[i];
        y_sum += y_samples[i];
    }
    int x_avg = x_sum / SAMPLE_COUNT;
    int y_avg = y_sum / SAMPLE_COUNT;
    
    // Read switch with debouncing
    bool switch_pressed = (digitalRead(PIN_SW) == LOW);
    
    // Send data
    Serial.print("JOYSTICK,");
    Serial.print(x_avg);
    Serial.print(",");
    Serial.print(y_avg);
    Serial.print(",");
    Serial.println(switch_pressed ? 1 : 0);
    
    // Check for calibration button press (hold for 2 seconds)
    if(switch_pressed) {
        delay(2000);
        if(digitalRead(PIN_SW) == LOW) {
            // Enter calibration mode
            Serial.println("CALIBRATION_STARTED");
            calibrate();
        }
    }
    
    delay(LOOP_DELAY);  // Reduced delay for better responsiveness
}

void calibrate() {
    int min_x = 4095, max_x = 0;
    int min_y = 4095, max_y = 0;
    unsigned long start_time = millis();
    const unsigned long CALIBRATION_TIME = 5000;  // 5 seconds
    
    // Clear any pending serial data
    while(Serial.available()) Serial.read();
    
    // Calibration loop
    while(millis() - start_time < CALIBRATION_TIME) {
        int x = analogRead(PIN_X);
        int y = analogRead(PIN_Y);
        
        min_x = min(min_x, x);
        max_x = max(max_x, x);
        min_y = min(min_y, y);
        max_y = max(max_y, y);
        
        // Show calibration in progress
        Serial.print("JOYSTICK,");
        Serial.print(x);
        Serial.print(",");
        Serial.print(y);
        Serial.println(",0");
        
        delay(10);
    }
    
    // Get center position
    int center_x = analogRead(PIN_X);
    int center_y = analogRead(PIN_Y);
    
    // Send calibration complete and center values
    Serial.println("CALIBRATION_COMPLETE");
    Serial.print("CENTER,");
    Serial.print(center_x);
    Serial.print(",");
    Serial.println(center_y);
} 