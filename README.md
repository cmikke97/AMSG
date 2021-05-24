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

# How to Run - Workflows

## Config file
The file `config.ini` contains the base configuration elements the user can tweak to change the tool workflow.

In particular this file contains the following elements:
1. Section `sorel20mDataset`
   - `training_n_samples`: max number of training data samples to use (if -1 -> takes all)
   - `validation_n_samples`: max number of validation data samples to use (if -1 -> takes all)
   - `test_n_samples`: max number of test data samples to use (if -1 -> takes all)
   - `validation_test_split`: (should not be changed) timestamp that divides the validation data (used to check convergence/overfitting) from test data (used to assess final performance)
   - `train_validation_split`: (should not be changed) timestamp that splits training data from validation data
   - `total_training_samples`: (should not be changed) total number of available training samples in the original Sorel20M dataset
   - `total_validation_samples`: (should not be changed) total number of available validation samples in the original Sorel20M dataset
   - `total_test_samples`: (should not be changed) total number of available test samples in the original Sorel20M dataset
1. Section `detectionBase`
   - `device`: desired device to train the model on, e.g. 'cuda:0' if a GPU is available, otherwise 'cpu'
   - `runs`: number of training runs to do
   - `batch_size`: how many samples per batch to load
   - `epochs`: how many epochs to train for
   - `use_malicious_labels`: whether or not to use malware/benignware labels as a target
   - `use_count_labels`: whether or not to use the counts as an additional target
   - `use_tag_labels`: whether or not to use the tags as additional targets
   - `gen_type`: generator type. Possible values are:
      - `base`: use basic generator (from the original SOREL20M code) modified to work with the pre-processed dataset
      - `alt1`: use alternative generator 1. Inspired by the 'index select' version of https://discuss.pytorch.org/t/dataloader-much-slower-than-manual-batching/27014/6, this version uses a new dataloader class, called FastTensorDataloader, to process tabular based data. It was modified from the original version available at the above link to be able to work with the pre-processed dataset (numpy memmap) and with multiple workers (in multiprocessing).
      - `alt2`: use alternative generator 2. Inspired by the 'shuffle in-place' version of https://discuss.pytorch.org/t/dataloader-much-slower-than-manual-batching/27014/6, this version uses a new dataloader class, called FastTensorDataloader, to process tabular based data. It was modified from the original version available at the above link to be able to work with the pre-processed dataset (numpy memmap) and with multiple workers (in multiprocessing).
1. Section `jointEmbedding`
   - `device`: desired device to train the model on, e.g. 'cuda:0' if a GPU is available, otherwise 'cpu'
   - `runs`: number of training runs to do
   - `batch_size`: how many samples per batch to load
   - `epochs`: how many epochs to train for
   - `use_malicious_labels`: whether or not to use malware/benignware labels as a target
   - `use_count_labels`: whether or not to use the counts as an additional target
   - `gen_type`: generator type. Possible values are:
      - `base`: use basic generator (from the original SOREL20M code) modified to work with the pre-processed dataset
      - `alt1`: use alternative generator 1. Inspired by the 'index select' version of https://discuss.pytorch.org/t/dataloader-much-slower-than-manual-batching/27014/6, this version uses a new dataloader class, called FastTensorDataloader, to process tabular based data. It was modified from the original version available at the above link to be able to work with the pre-processed dataset (numpy memmap) and with multiple workers (in multiprocessing).
      - `alt2`: use alternative generator 2. Inspired by the 'shuffle in-place' version of https://discuss.pytorch.org/t/dataloader-much-slower-than-manual-batching/27014/6, this version uses a new dataloader class, called FastTensorDataloader, to process tabular based data. It was modified from the original version available at the above link to be able to work with the pre-processed dataset (numpy memmap) and with multiple workers (in multiprocessing).
1. Section `freshDataset`:
   - `signatures`: malware Bazaar families of interest. NOTE: It is recommended to specify more families than 'number_of_families' since Malware Bazaar may not have 'amount_each' samples for some of them. These families will be considered in order.
   - `number_of_families`: number of families to consider. The ones in excess, going in order, will not be considered.
   - `amount_each`: amount of samples for each malware family to retrieve from Malware Bazaar
   - `queries`: number of queries to do in model (fresh) evaluation

## Joint Embedding Workflow (main)

Command used to activate an entire Automatic Malware Signature Generation MLflow workflow using values set in <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#config-file' title='config file'>config file</a>.
In particular the workflow is composed of the following steps:
1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#dataset-download' title='Dataset Download'>Dataset Download</a> (if both the pre-processed and the original SOREL20M dataset are not present on disk)
1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#pre-process-dataset' title='Pre-Process Dataset'>Pre-Process Dataset</a> (if the pre-processed dataset is not present on disk)
1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#build-fresh-dataset' title='Build Fresh Dataset'>Build Fresh Dataset</a> (if the fresh dataset is not present on disk)
1. For 'runs' (configurable in <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#config-file' title='config file'>config file</a>) times:
    1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#train-network' title='Train Network'>Train Network</a>
    1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#evaluate-network' title='Evaluate Network'>Evaluate Network</a>
    1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#plot-tag-results' title='Plot Tag Results'>Plot Tag Results</a>
    1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#compute-all-scores' title='Compute All Scores'>Compute All Scores</a>
    1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#compute-mean-scores' title='Compute Mean Scores'>Compute Mean Scores</a>
    1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#evaluate-fresh' title='Evaluate Fresh'>Evaluate Fresh</a>
1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#plot-all-roc-distributions' title='Plot All ROC Distributions'>Plot All ROC Distributions</a>
    
```
mlflow run /content/Automatic-Malware-Signature-Generation \
-P base_dir=<tool destination dir>
```

---
## Base Detection Workflow

Command used to activate an entire Base detection MLflow workflow using values set in <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#config-file' title='config file'>config file</a>.
In particular the workflow is composed of the following steps:
1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#dataset-download' title='Dataset Download'>Dataset Download</a> (if both the pre-processed and the original SOREL20M dataset are not present on disk)
1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#pre-process-dataset' title='Pre-Process Dataset'>Pre-Process Dataset</a> (if the pre-processed dataset is not present on disk)
1. For 'runs' (configurable in <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#config-file' title='config file'>config file</a>) times:
    1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#train-network' title='Train Network'>Train Network</a>
    1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#evaluate-network' title='Evaluate Network'>Evaluate Network</a>
    1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#plot-tag-results' title='Plot Tag Results'>Plot Tag Results</a>
    1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#compute-all-scores' title='Compute All Scores'>Compute All Scores</a>
    1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#compute-mean-scores' title='Compute Mean Scores'>Compute Mean Scores</a>
1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#plot-all-roc-distributions' title='Plot All ROC Distributions'>Plot All ROC Distributions</a>
```
mlflow run /content/Automatic-Malware-Signature-Generation -e detection_workflow \
-P base_dir=<tool destination dir>
```

---
# How to Run - Single steps
## Dataset Download

Command used to download SOREL20M dataset elements from the s3 socket and save them in the specified destination directory on the current machine.
```
mlflow run <Automatic-Malware-Signature-Generation dir path> -e download_dataset \
-P destination_dir=<path to the destination folder where to save the element to>
```

---
## Pre-process Dataset
### Pre-process Dataset

Command used to pre-process SOREL20M dataset transforming it to a more easy (and quick) to read dataset format.
```
mlflow run /content/Automatic-Malware-Signature-Generation -e preprocess_dataset \
-P ds_path=<path to the directory containing the meta.db file> \
-P destination_dir=<the directory where to save the pre-processed dataset files> \
-P training_n_samples=<max number of training data samples to use (if -1 -> takes all) (default: -1)> \
-P validation_n_samples=<max number of validation data samples to use (if -1 -> takes all) (default: -1)> \
-P test_n_samples=<max number of test data samples to use (if -1 -> takes all) (default: -1)> \
-P batch_size=<how many samples per batch to load (default: 8192)> \
-P remove_missing_features=<Strategy for removing missing samples, with meta.db entries but no associated features, from the data>
```

Note on remove_missing_features: it can be False/None/'scan'/filepath. In case it is 'scan' a scan will be performed on the database
in order to remove the data points with missing features; in case it is a filepath then a file (in Json format) will be used to
determine the data points with missing features.

### Alternative

If the current machine/instance disk capacity is not enough to contain both the original SOREL20M dataset and the newly created pre-processed dataset use this alternative procedure:
1. First pre-process the dataset transforming it to the same format as in the previous command but saving it in multiple files on another disk (I used Google Colab drive for the original SOREL20M dataset and Google Drive for the pre-processed files).
You may now want get rid of the original dataset since it is not anymore needed. 
1. The final step needed to have the final pre-processed dataset (the same you would have gotten using the previous command), combine all the generated multipart files.

#### Pre-process Dataset Multipart

```
mlflow run /content/Automatic-Malware-Signature-Generation -e preprocess_ds_multi \
-P ds_path=<path to the directory containing the meta.db file> \
-P destination_dir=<the directory where to save the pre-processed dataset files> \
-P training_n_samples=<max number of training data samples to use (if -1 -> takes all) (default: -1)> \
-P validation_n_samples=<max number of validation data samples to use (if -1 -> takes all) (default: -1)> \
-P test_n_samples=<max number of test data samples to use (if -1 -> takes all) (default: -1)> \
-P batch_size=<how many samples per batch to load (default: 8192)> \
-P n_batches=<number of batches to save in one single file (if -1 -> takes all) (default: 10)> \
-P remove_missing_features=<Strategy for removing missing samples, with meta.db entries but no associated features, from the data>
```
Note on remove_missing_features: it can be False/None/'scan'/filepath. In case it is 'scan' a scan will be performed on the database
in order to remove the data points with missing features; in case it is a filepath then a file (in Json format) will be used to
determine the data points with missing features.

#### Combine Dataset Multipart Files

```
mlflow run /content/Automatic-Malware-Signature-Generation -e combine_ds_files \
-P ds_path=<local_multi_path> \
-P training_n_samples=<max number of training data samples to use (if -1 -> takes all) (default: -1)> \
-P validation_n_samples=<max number of validation data samples to use (if -1 -> takes all) (default: -1)> \
-P test_n_samples=<max number of test data samples to use (if -1 -> takes all) (default: -1)>
```

---
## Train Network

Command used to train the (chosen) feed-forward neural network on EMBER 2.0 features, optionally with additional targets as described in the ALOHA paper (https://arxiv.org/abs/1903.05700). SMART tags based on (https://arxiv.org/abs/1905.06262).
```
mlflow run /content/Automatic-Malware-Signature-Generation -e train_network \
-P ds_path=<path of the directory where to find the pre-processed dataset (containing .dat files)> \
-P net_type=<network to use between 'JointEmbedding' and 'DetectionBase' (default: jointEmbedding)> \
-P gen_type=<generator (and dataset) class to use between 'base', 'alt1', 'alt2' (default: base)> \
-P run_id=<mlflow run id of a previously stopped run to resume (default: 0)> \
-P training_run=<training run identifier (default: 0)> \
-P batch_size=<how many samples per batch to load (default: 8192)> \
-P epochs=<how many epochs to train for (default: 10)> \
-P training_n_samples=<number of training samples to consider (-1 -> take all) (default: -1)> \
-P validation_n_samples=<number of validation samples to consider (-1 -> take all) (default: -1)> \
-P use_malicious_labels=<whether or not (1/0) to use malware/benignware labels as a target (default: 1)> \
-P use_count_labels=<whether or not (1/0) to use the counts as an additional target (default: 1)> \
-P use_tag_labels=<whether or not (1/0) to use the tags as additional targets (default: 1)>
```

---
## Evaluate Network

Command used to produce and output (to a csv file) evaluation results for a trained feedforward neural network model.
```
mlflow run /content/Automatic-Malware-Signature-Generation -e evaluate_network \
-P ds_path=<path of the directory where to find the pre-processed dataset (containing .dat files)> \
-P checkpoint_file=<path to the model checkpoint to load> \
-P net_type=<network to use between 'JointEmbedding' and 'DetectionBase' (default: jointEmbedding)> \
-P gen_type=<generator (and dataset) class to use between 'base', 'alt1', 'alt2' (default: base)> \
-P batch_size=<how many samples per batch to load (default: 10)> \
-P test_n_samples=<number of test samples to consider (-1 -> take all) (default: -1)> \
-P evaluate_malware=<whether or not (1/0) to record malware labels and predictions (default: 1)> \
-P evaluate_count=<whether or not (1/0) to record count labels and predictions (default: 1)> \
-P evaluate_tags=<whether or not (1/0) to use SMART tags as additional targets (default: 1)>
```

---
## Plot Tag Results

Command used to produces multiple overlaid ROC plots for each tag individually, from a result file got from a feedforward neural network model that includes all tags.
```
mlflow run /content/Automatic-Malware-Signature-Generation -e plot_tag_result \
-P results_file=<path to results.csv containing the output of a model run>
```

---
## Compute All Scores

Command used to compute a bunch of per-tag scores (tpr at fpr, accuracy, recall, precision and f1-score) of a training run, from a result file.
```
mlflow run /content/Automatic-Malware-Signature-Generation -e compute_all_scores\
-P results_file=<path to results.csv containing the output of a model run>
```

---
## Compute Mean Scores

Command used to estimate some mean, per-sample, scores (jaccard similarity and mean per-sample accuracy) for a dataframe at specific False Positive Rates of interest
```
mlflow run /content/Automatic-Malware-Signature-Generation -e compute_mean_scores \
-P results_file=<path to results.csv containing the output of a model run>
```

---
## Plot All ROC Distributions

Command used to compute the mean and standard deviation of the TPR at a range of FPRS (the ROC curve) over several sets of results (at least 2 runs) for a given tag.
The run_to_filename_json file must have the following format:
```
{"run_id_0": "/full/path/to/results.csv/for/run/0/results.csv",
 "run_id_1": "/full/path/to/results.csv/for/run/1/results.csv",
  ...
}
```
```
mlflow run /content/Automatic-Malware-Signature-Generation -e plot_all_roc_distributions \
-P run_to_filename_json=<path to the run_to_filename_json file>
```

---
## Build Fresh Dataset

Command used to build a 'fresh' dataset retrieving samples from Malware Bazaar given a list of malware families stored in a configuration file.
```
mlflow run /content/Automatic-Malware-Signature-Generation -e build_fresh_dataset \
-P dataset_dest_dir=<dir where to write the newly created dataset>
```

---
## Evaluate Fresh

Command used to produce and output (to a json file and a bunch of csv files) fresh dataset evaluation results for a trained feedforward neural network model.
```
mlflow run /content/Automatic-Malware-Signature-Generation -e evaluate_fresh \
-P ds_path=<path of the directory where to find the fresh dataset (containing .dat files)> \
-P checkpoint_path=<path to the model checkpoint to load> \
-P n_queries=<number of queries to do (default: 100)>
```

---

# Wiki
There is now a <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki' title='Wiki!'>📖wiki</a>!
