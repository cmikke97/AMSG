# AMSG
Automatic Malware Signature Generation Tool.

# Description

# Requirements

The tool exploits <a href='https://mlflow.org/' title='mlflow'>mlflow</a> open source platform ot package the code in a reusable and reproducible way, to manage the running environment and log results.
Moreover, the project environment is based on a <a href='https://docs.conda.io/en/latest/' title='Conda'>Conda</a> environment.

Therefore, to run this code, it is necessary to have installed both <a href='https://mlflow.org/' title='mlflow'>mlflow</a> and <a href='https://docs.conda.io/en/latest/' title='Conda'>Conda</a>:
- To install <a href='https://mlflow.org/' title='mlflow'>mlflow</a> you can use: `pip install -q mlflow`.
- To install <a href='https://docs.conda.io/en/latest/' title='Conda'>Conda</a>, please refer to https://www.anaconda.com/products/individual or https://docs.conda.io/en/latest/miniconda.html

Further necessary packages will be downloaded automatically.

# How to Run
## Dataset Download

Command used to download SOREL20M dataset elements from the s3 socket and save them in the specified destination directory on the current machine.
```
!mlflow run <Automatic-Malware-Signature-Generation dir path> -e download_dataset \
-P destination_dir=<dataset_destination_path>
```

---
## Pre-process Dataset
### Pre-process Dataset
### Alternative
#### Pre-process Dataset Multipart
#### Combine Dataset Multipart Files

---
## Train Network

---
## Evaluate Network

---
## Plot Tag Results

---
## Compute All Scores

---
## Compute Mean Scores

---
## Plot All ROC Distributions

---
## Build Fresh Dataset

---
## Evaluate Fresh

---
## Joint Embedding Workflow (main)

---
## Base Detection Workflow

---

# Wiki
There is now a <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki' title='Wiki!'>📖wiki</a>!
