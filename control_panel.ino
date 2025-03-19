#include <Servo.h>

// Pin definitions for potentiometers
#define NUM_POTS 7
const int potPins[NUM_POTS] = {A10, A1, A7, A3, A4, A5, A6}; // Changed A7 to A2

// Variables to store pot values
int potValues[NUM_POTS];
int lastPotValues[NUM_POTS];
int rawValues[NUM_POTS];

// Smoothing parameters
const float SMOOTHING_FACTOR = 0.5; // Increased for less lag (0.2 -> 0.5)
const int DEADZONE = 1; // Reduced deadzone for more responsiveness

// Calibration values - adjust these based on your potentiometers
const int MIN_POT_VALUE = 0;
const int MAX_POT_VALUE = 1023;

// Device identifier - to distinguish from throttle quadrant
const char DEVICE_ID[] = "CTRLPANEL";

void setup() {
  Serial.begin(115200);
  
  // Set analog reference to DEFAULT (5V on most boards)
  analogReference(DEFAULT);
  
  // Add a small delay between analog reads to reduce crosstalk
  // analogReadResolution(10); // Removed - not supported on all Arduino boards
  
  // Initialize arrays
  for (int i = 0; i < NUM_POTS; i++) {
    // Read each pot a few times to stabilize the ADC
    for (int j = 0; j < 5; j++) {
      analogRead(potPins[i]);
      delay(1);
    }
    
    // Initialize with actual readings
    rawValues[i] = analogRead(potPins[i]);
    potValues[i] = rawValues[i];
    lastPotValues[i] = rawValues[i];
  }
  
  // Wait for serial connection
  delay(500);
  Serial.println("CTRLPANEL,Initializing...");
}

void loop() {
  // Read all potentiometers with improved technique
  for (int i = 0; i < NUM_POTS; i++) {
    // Take multiple readings and average them
    int sum = 0;
    for (int j = 0; j < 3; j++) {
      sum += analogRead(potPins[i]);
      delayMicroseconds(500); // Small delay between readings
    }
    rawValues[i] = sum / 3;
    
    // Apply smoothing
    potValues[i] = (SMOOTHING_FACTOR * rawValues[i]) + ((1.0 - SMOOTHING_FACTOR) * potValues[i]);
    
    // Only update if the change is significant
    if (abs(potValues[i] - lastPotValues[i]) <= DEADZONE) {
      potValues[i] = lastPotValues[i];
    } else {
      lastPotValues[i] = potValues[i];
    }
    
    // Invert the values (1023 - value)
    rawValues[i] = MAX_POT_VALUE - rawValues[i];
    potValues[i] = MAX_POT_VALUE - potValues[i];
  }
  
  // Send data in CSV format with device identifier
  Serial.print(DEVICE_ID);
  for (int i = 0; i < NUM_POTS; i++) {
    // Send both raw and processed values
    Serial.print(",");
    Serial.print(rawValues[i]); // Send raw value first
    Serial.print(",");
    Serial.print(potValues[i]); // Send smoothed value second
  }
  Serial.println();
  
  // Reduced delay for less lag
  delay(10);
} 