List of TODOs:

---Helper functions---
* Add checking of user input, in case it is out of bounds, ignore the input and print some message
* Add calculation of current position and position query for bound limits
* Recheck the movement procedures in the device class
* Add the deposition parameter functions from the paper to help with the deposition

---Initialising---
* Add initial position capabilities
* Create an input parameter for checking if the needle is touching the substrate
* Program the ability to be enabled by touch
* Map out the substrate as you touch them to ensure the same gap height everywhere before deposition starts (only on first deposition and outside the bounds of the deposition)

---Deposition---
* Add speed profiles for movement and deposition
* Add a pressure control for the syringe pump
* Add pressure dependancy on the inner nozzle diameter


extra:
* set limits of deposition movement only to the size of the table by using calculation of current position of x and y

we go with v* = 4Q/pi(ID)^2v
where Q is flow rate (lets call it um/s) = variable
ID is inner diameter = 0.06 mm
v is the stage speed = variable

h_0/ID has to be between 0.03 and 0.21
v* has to be between 0.05 and 1

the maximum gap height is therefore 0.21*0.06 = 0.0126

lets hit for raneg 5 -10 microns to be sure -> 10 is gold

with that we have a 10 micron height set 

to get the line height of 20 microns

H = 2.1h_0 - 0.03ID

h_0 = (20 + 0.03*0.02)/2.1

h_0 ~ 10 um

Calculate the force through Hagen-Poiseuille