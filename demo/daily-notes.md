6/17/26
Ashkan:
Implemented the revel/spliceai tool. Updated the plan agent because it had an issue parsing through some files. 
I got PP3 and PM2_SUPPORTING to both run, and revealed that they both applied correctly (agrees with VCEP).
Note that when running pipeline.py, the imports themselves take about 1.5 minutes to run before the LLM even gets to thinking.
Additionally, my agent was able to correctly identify that PM2_SUPPORTING, PP3 apply, while BP4 does that. I specifically tried those criterion because I have created the tools for them. 

6/22/26
Implement PM4 and PVS1. The pipeline is running, but I haven't got time to check whether it is producing the correct result. (I am not very sure about which transcript I should select)
Tomorrow morning I will have a driving test so maybe I won't have time to add a lot of things tomorrow. 

What I plan to work on over the next two days: 
- Add one more tools
- Change the rag to a real rag
- combing the variant annotation tool in utils.py with the same variant annotation tool in vep.py
- Let the pipeline run in parallel with each other

## Commands to run the pipeline
```bash
python3.14 demo/pipeline.py --variant "NM_000020.3:c.557G>T" --disease "HHT"
```




6/22/26:
Implemented tools for PM1 (uses VEP, expanded VEP to get information for PM1), PS4, PS1, PM5. At the end of the day, the pipeline ran into trouble while calling APIs, it seemed all APIs were down (Ensemble for annotation, Gnomad for PM2_Supporting)