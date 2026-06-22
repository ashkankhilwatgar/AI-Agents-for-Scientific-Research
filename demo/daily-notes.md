6/17/26
Ashkan:
Implemented the revel/spliceai tool. Updated the plan agent because it had an issue parsing through some files. 
I got PP3 and PM2_SUPPORTING to both run, and revealed that they both applied correctly (agrees with VCEP).
Note that when running pipeline.py, the imports themselves take about 1.5 minutes to run before the LLM even gets to thinking.
Additionally, my agent was able to correctly identify that PM2_SUPPORTING, PP3 apply, while BP4 does that. I specifically tried those criterion because I have created the tools for them. 


6/22/26:
Implemented tools for PM1 (uses VEP, expanded VEP to get information for PM1), PS4, PS1, PM5. At the end of the day, the pipeline ran into trouble while calling APIs, it seemed all APIs were down (Ensemble for annotation, Gnomad for PM2_Supporting)