6/17/26
Ashkan:
Implemented the revel/spliceai tool. Updated the plan agent because it had an issue parsing through some files. 
I got PP3 and PM2_SUPPORTING to both run, and revealed that they both applied correctly (agrees with VCEP).
Note that when running pipeline.py, the imports themselves take about 1.5 minutes to run before the LLM even gets to thinking.
Additionally, my agent was able to correctly identify that PM2_SUPPORTING, PP3 apply, while BP4 does that. I specifically tried those criterion because I have created the tools for them. 


6/22/26:
Implemented tools for PM1 (uses VEP, expanded VEP to get information for PM1), PS4, PS1, PM5. At the end of the day, the pipeline ran into trouble while calling APIs, it seemed all APIs were down (Ensemble for annotation, Gnomad for PM2_Supporting)

6/23/26:
Try to let the agents run in parallel. I create a new custom branch and push the changes there. (I only changes pipeline.py). It is not working. Seems that if we let too many agents run in parallel then we will easily be banned because we are calling apis too frequently. (At least it did not work with gemini api, but maybe it works with ollama I guess?).
If you want to run the new pipeline in the custom branch here is the updated bash command:

```bash
python3.14 demo/pipeline.py \
  --variant "NM_000020.3:c.557G>T" \
  --disease "HHT" \
  --max-concurrency 2
```
where max-concurrency controls how many agents are running in parallel with each other


6/24/26
Simon: 
Finish (I guess) implementing the functional evidence tool that checks PS3/BS3. I have not integrate the tools into the pipeline so currently the pipeline **cannot** check PS3/BS3! Still working on parallelizing the pipeline. 

