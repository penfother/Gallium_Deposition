List of TODOs:

---Logging---
* Create ability to log in the movements of the machine
* Add checking of user input, in case it is out of bounds, ignore the input and print some message
* Add calculation of current position and position query for bound limits
* Recheck the movement procedures in the device class

---Initialising---
* Add initial position capabilities
* Create an input parameter for checking if the needle is touching the substrate
* Program the ability to be enabled by touch
* Map out the substrate as you touch them to ensure the same gap height everywhere before deposition starts (only on first deposition and outside the bounds of the deposition)

---Deposition---
* Add plunger travel calculation for a specific amount  of gallium
* Add volume calculation for syringe
* Add speed profiles for movement and deposition
* Add a pressure control for the syringe pump



extra:
* set limits of deposition movement only to the size of the table by using calculation of current position of x and y