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




6/29/26
Ashkan
Fixed some prompts for a few criterion, got started on incorporation more VCEPs

7/6/26
SIMON
* I downgraded my Python version to 3.12 so we no longer need to worry about compatibility issues.
* I am currently writing the evaluation script.
  - I created a folder called "evaluation" and added four files inside it (question1.py, question2.py, question3.py, and question4.py). In our shared Google Doc, the professor provides nine questions. I planned a one-file-per-question structure, so I created files for the first four questions, but I have only implemented the code for question 2 so far.
  - question2.py currently has some logic errors.

Current issues with question2.py

- Issue 1: Confusion matrix
question2.py currently only handles a binary confusion matrix like this:
        predicted
        0   1   
true    8   0   

However, question 2 requires a multi-class confusion matrix like this:

                  predicted
            0   1   2   3   4

     0      8   0   1   0   0
     1      0   7   0   2   0
true 2      1   0   6   1   0
     3      0   1   2   9   1
     4      0   0   0   3   10

This is because question 2 evaluates the overall classification outcome, which includes classes such as benign, likely benign, VUS, likely pathogenic, and pathogenic, rather than a simple binary apply/non-apply decision.

While writing the code, I assumed a binary confusion matrix format, which was incorrect. During testing, I realized that the binary version corresponds to question 1 (single criterion evaluation), while question 2 requires a multi-class confusion matrix for the full pipeline evaluation.

- Issue 2: Currently, question2.py cannot handle cases where the final result contains an error. In such cases, we need to decide whether the pipeline should count it as a mistake.

- There may also be some other syntax issues.

If you try to run the code (although it is not working properly right now), you can use the command: 
```bash
python -m evaluation.question2 --gold_answer_csv_filename full_evaluation_dataset.csv --model_output_json_filename outputs/batch_20260706_161031/batch_summary.json --output_dir evaluation/outputs
```

I'll come backt o question2.py tomorrow morning. If you guys think having one file per question is a bad idea, you can feel free to change/delete question2.py
python -m evaluation.question2 --gold_answer_csv_filename full_evaluation_dataset.csv --model_output_json_filename outputs/batch_20260708_132813/batch_summary.json --output_dir evaluation/outputs


7/7/26
Ashkan
I did one case study for 25 variants that our pipeline could absolutely classify, and got a 91% success rate. I changed the code a little bit, but they were minor things.
Suning created a script for Q3, and I uploaded it here.

7/8/26 Simon
I take a look at the case study and try to analyze the result. Here is what I get:

- By the way here is the result of Ashkan's case study

accuracy: 0.84
precision: 0.9136363636363637
recall: 0.7980952380952381
F1: 0.8177777777777777
number of failed variants: 0

Confusion Matrix:
            Pred B  Pred LB  Pred VUS  Pred LP  Pred P
Actual B         1        0         0        0       0
Actual LB        0        4         1        0       0
Actual VUS       0        0         9        0       0
Actual LP        0        0         1        6       0
Actual P         0        0         0        2       1

- Precision is higher than recall. Precision is higher when most of the variants are actually pathogenic/benign/etc... when our prototype said it is pathogenic/benign/etc... Recall is higher when our prototype can identify most of the pathogenic/benign/etc... variants. Precision is higher than recall means our model is more conservative than comprehensive, which means our prototype hesitate to say a variant is pathogenic/benign/etc... But when it indeed says so, it is mostly correct.
- Therefore, I take a look at the variants. There are four variants that are incorrectly classified:

```json
[
  {
    "variant_name": "NM_001114753.3:c.1701del",
    "correct_or_not": false,
    "gold_classification": "Pathogenic",
    "predicted_classification": "Likely Pathogenic",
    "golden_criterion": ["PVS1", "PM2_supporting", "PS4_supporting"],
    "predicted_criterion": ["PVS1", "PM2_supporting"]
  },
  {
    "variant_name": "NM_000020.3:c.1348A>G",
    "correct_or_not": false,
    "gold_classification": "Likely Benign",
    "predicted_classification": "Variant of Uncertain Significance (VUS)",
    "golden_criterion": ["BS1"],
    "predicted_criterion": ["BS1"]
  },
  {
    "variant_name": "NM_000020.3:c.1217G>A",
    "correct_or_not": false,
    "gold_classification": "Pathogenic",
    "predicted_classification": "Likely Pathogenic",
    "golden_criterion": ["PVS1", "PM2_Supporting", "PS4_Supporting"],
    "predicted_criterion": ["PVS1", "PM2_Supporting"]

  },
  {
    "variant_name": "NM_000020.3:c.293A>G",
    "correct_or_not": false,
    "gold_classification": "Likely Pathogenic",
    "predicted_classification": "Variant of Uncertain Significance (VUS)",
    "golden_criterion": ["PM2_Supporting", "PS3_Supporting", "PS4"],
    "predicted_criterion":["PM2_SUPPORTING", "PS4"]
  }
]
```
- Seems that the problems are 
  * There is problem with PS4. We failed at PS4 three times.
  * There is problem with the final classification logic. For the second variant, same applied criterion have different final classification.
  * PS3 also failed once. Maybe we also need to work on that (PS3 is the one that we use llm to read anstract of papers, so this can be unstable. I am satisfied with 1/25 error rate, but maybe there are also other undetected reasoning errors w/ PS3 while we are evaluating other variants.)
  * Seems that criterions that we cannot check didn't cause a problem here. Maybe VCEP expert panels also didn't check those criterions that are deemed uncheckable.


7/8/26
Ashkan

 {
    "variant_name": "NM_000020.3:c.1348A>G",
    "correct_or_not": false,
    "gold_classification": "Likely Benign",
    "predicted_classification": "Variant of Uncertain Significance (VUS)",
    "golden_criterion": ["BS1"],
    "predicted_criterion": ["BS1"]
  },

  for this failed classification, the pipeline applied BS1 at a supporting level, which comes out as VUS in the final classification. 

7/9
I copied Simon's case study fo all 200 variants, but only included the 48 variants that actually have criteria that apply to them. The results changed a bit.The accuracy was about 94%.
I also ran the pipeline on all 200 variants for the ablation study, so that will take around 8 hours. 

python -m evaluation.question1 --gold_answer_csv_filename applied_only_evaluation_dataset.csv --model_output_json_filename outputs/batch_20260708_132813/batch_summary.json --output_dir evaluation/outputs

7/10 Simon

Continue doing case study + cleaning up the file sturcture. See my case studies at case_studies/jul_10/case_study_summary.md

7/13 SIMON
IMPORVE THE TOOL RESULT CACHING SO THAT IF IN THE PREVIOUS PHASE THE TOOL RESULT IS "ERROR" IN CURRENT PHASE WE WILL RUN THE TOOL AGAIN INSTEAD OF BLINDLY USE THE "ERROR" RESULT. ALSO DID A CASE STDUY ON PS3 & BS3 (SEE case_studies/jul_13/bs3_ps3_case_study.ipynb)\

7/14 Ashkan
I created the UI, it can be run like this: venv/bin/python -m gui.server. Note that it takes about 3 minutes for everything to load, and if you actually want to classify a variant, it takes like 30 minutes. There is a cache result for every variant already classified, and those can be loaded. Tomorrow I want to finish question 9.∂


7/15 Suning

Changed bs3 ps3 planrag and changed all the fstring so that it is downgraded to python 3.10.

7/21
Ashkan

I cleaned up any dead code, wrote a good readme file, and started working on the baseline. To run the baseline, use the command python -m baseline.run_baseline --limit 3 --passes 1. This is just as an example, it will take the first 3 variants from the full_evaluation_dataset. I also created a script to evaluate the baseline results, and here is the way to run that: venv/bin/python -m baseline.evaluate_baseline