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
Working on implementing the functional evidence tool that checks PS3/BS3. I have not integrate the tools into the pipeline so currently the pipeline **cannot** check PS3/BS3! 


6/24/26 Ashkan
python3.12 -m pipeline --variant "NM_001114753.3:c.1701del" --disease "HHT"
python3.12 -m pipeline --variant "NM_000020.3:c.151T>G" --disease "HHT"

Created a gene database in preparation for incorporating more VCEPs
Created another tool for PS4 called LOVD. A lot of data is just missing, and PS4 is falsely not being applied because the data does not exist in VEP or clinvar.
Removed a redundant reasoning by plan agent, this cuts down pipeline time by 50% I think.
Changed the API lookup for clinvar and VEP so that frameshift and other sorts of variants can be detected.
Created a method that filters out criterion based on what sort of variant exists. 


6/25/26 Simon
Finish integrating the tool that check Bs3/PS3. Current the tool will fetch relevant literatures from pubmed and scan their abstract to find available functional evidence. The pipeline also supports download pdf to the project folder and then use llm to read the pdf, which enables more accurate functional_evidence retrieval. However, because that is too complicated for us right now, I only enable evidence retieval from abstract. But if we want we can add pdf retrieval at any time. I have also updated the planrag to reflect the fact that we can actually automate BS3/PS3. 

For the current variant that we are testing: 
```bash
python3.14 demo/pipeline.py --variant "NM_000020.3:c.557G>T" --disease "HHT"
```
The functional evidence tool cannot check BS3/PS3 because literature retrieval requires rsid and this variant does not have a rsid. Currently this tool will return an empty output when the variant does not have an rsid and the prompt in the planrag will instruct our models to "classify BS3&PS3 as not applied when the tool's output is empty". This is also how other tools tha only check automatable codes do: set all the codes that are not automatable to not applied. However, we can change this behavior later.

I reimplement the llm wrappers because they are needed for the functional_evidence tool. Here are the documentations for the new llm wrapper.
  - **You don't need to do anything at all**. If there is no bug (because I didn't experiment with the new llm wrapper on ollama servers), you can just run the pipeline using our previous bash command python3.14 demo/pipeline.py --variant "NM_000020.3:c.557G>T" --disease "HHT".

If you want to use an external api, such as glm5.2 or gpt5.5, you can just go to config.py and change the model providers and model names in **MODELS**. Supported providers and models are (not exhaustive):
    - {"provider": "openai", "models": ["gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"]}
    - {"provider": "google_genai", "models": ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.5-pro", "gemini-2.5-flash", "gemini-3.1-pro", "gemini-3.1-flash"]}
    - {"provider": "z.ai", "models": ["glm-5.2"]}  # In case you want to use z.ai models

Note that, however, if you want to use external models you must cp .env.example .env and replace whatever api key correspond to your model provider with your owns.

Again, if you just want to use the ollama models we don't need to do anything.

Tomorrow I will come back to implementing parallel agent architecture.



6/26 Suning

1. Command line to test SPAST splice variant (the one that should be Pathogenic):
ACMG python3.12 -m pipeline --variant "NM_014946.4:c.1688-2A>G" --disease "ACMG"

2. Command line to test the TMCC2 missense (the one with PM5/PS1/BP1 failures):

```bash
python3 -m pipeline --variant "NM_014858.4:c.1676G>A" --disease "ACMG"
```


06/29/2026 Simon
1. Finish implementing parallel agents. Currently I didn't comment out all the print statements, but do note that as we let agents run in paralle the print statements do get messy. 
2. My next step is to try to implement a real rag. Hopefully I will finish that tomorrow. I will also think about other langgraph & langchain tools that we can use in our pipeline.
3. The pipeline runtime is approximately 1.5 to 2 min after implementing the parallel agents. 
4. I also run our pipeline on the first transcript (NM_000020.3:c.557G>T). The result is (for that variant only PP4_moderate, PM2_supporting, PS4_moderare, and PP3 holds, and currently we don't check PP4_moderate so I only look at PM2_supporting, PS4_moderare, and PP3 )
  - Round 1:  PM2_supporting, PS4_moderare -> Correct; PP3 -> Incorrect; PM5, PS1 -> failed
  - Round 2: PM2_supporting, PS4_moderare, PP3 -> Correct; PM5, PS1 -> failed
  - Round 3: PM2_supporting, PS4_moderare, PP3 -> Correct; PM5, PS1 -> failed

07/01/2026
Let the agents always produce structured output by feeding it an output schema. 




