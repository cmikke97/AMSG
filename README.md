# AMSG
Automatic Malware Signature Generation Tool.

This tool was developed as a thesis project at the TORSEC research group of the Polytechnic of Turin (Italy) under the supervision of professor Antonio Lioy and engineer Andrea Atzeni and with the support of engineer Andrea Marcelli.

The thesis document describing this tool is available at this <a href='https://github.com/cmikke97/Thesis' title='Thesis Document'>github repository</a>.

# Description - Summary
In most recent years the proliferation of malicious software, namely Malware, has had a massive increase: according to AV Atlas in 2019 and 2020 (and until mid 2021 - that is until the time of writing) the number of newly generated malware blew with respect to previous years to the point that approximately 5,1 new Microsoft Windows malware (and PUA – Potentially Unwanted App) are currently generated per second, ~18.500 per hour and ~440.000 per day. The total amount of unique malware (and PUA) variants has nowadays reached impressive numbers, to the point that more than 830 million are now reported by AV Atlas Dashboard. Moreover, nowadays malware commonly use obfuscation and other sophisticated techniques, such as Polymorphism and Metamorphism, to evolve their structure thus evading detection.

For all these reasons signature-based detection techniques (such as manually generated Yara Rules), which are typically used by most commercial anti-virus solutions, are becoming inefficient in the present scenario. In fact, it is now straight up impossible for analysts to manually analyse each malware variant that is found in the wild. Furthermore, even when a new malware family is identified and an appropriate amount of its samples are analysed, the generated signature may not be capable of detecting new variations or may even be rendered useless through the use of obfuscation and/or polymorphic mechanisms. There is therefore the need for automated malware analysis solutions capable of automatically generating (implicit or explicit) signatures effective at distinguishing malicious from benign code while being less susceptible to code modifications and obfuscation attempts.

This thesis presents a research aimed at satisfying this need for automated malware detection solutions. In particular, it presents a novel model built upon previous works on ML-based (Machine Learning based) automatic malware detection and description designed for <b>PE</b> (Microsoft Windows Portable Executable) files. Moreover, it introduces a new evaluation procedure that may prove the applicability of the model learned implicit representation/signature of malware samples in the Malware family prediction and ranking tasks. These tasks are particularly interesting for malware analysts since they allow them to quickly categorize malware samples as being part of specific sets (families) with common behavioural and structural characteristics.

The proposed framework life cycle can be conceptually divided in four phases: <b>model architecture definition</b>, <b>model training and validation</b>, <b>model evaluation</b> and finally <b>model deployment</b>. In particular, in the first phase the proposed <b>FNN</b> (Feedforward Neural Network) model architecture, called <b>Multi Task Joint Embedding</b> (<b>MTJE</b>), is defined and implemented taking inspiration from previous works such as the <b>ALOHA</b> and the <b>Joint Embedding</b> models presented by Rudd et al. and  Ducau et al. in the respective papers. In the second phase, instead, the proposed <b>MTJE</b> model is trained (and validated) on an open source large scale dataset of malware and benignware samples (<b>Sorel20M</b> by Harang et al.) with the aim of creating high quality implicit signatures capable of detecting (and describing via SMART tags) unseen malware samples, as well as obfuscated malware and new variants, with high True Positive Rate (TPR) and high Recall at low False Positive Rates (FPRs). The first two phases here described are iteratively repeated until a model with satisfactory training and validation loss trends is generated. In the third phase, on the other hand, the final model architecture is tested on the <b>Malware detection</b> and <b>description</b> tasks and the corresponding prediction scores are computed and plotted. Moreover, in this phase the model learned representation of PE files is also tested on the <b>Malware family prediction</b> and <b>ranking</b> tasks using a novel dataset, referred to as '<b>Fresh Dataset</b>', containing 10.000 samples belonging to 10 of the most widespread malware families in Italy at the time of writing, specifically created for that purpose. In both datasets the samples are directly represented by the numerical feature representation extracted statically from specific fields of their Windows Portable Executable (PE) file header. The <b>MTJE</b> model thus relies exclusively on static analysis features which are generally simpler, less computationally intensive and thus faster than dynamic analysis ones (behavioural characteristics of executables). Finally, in the last phase the final model architecture is deployed in the wild. In particular, it can be used as an automatic malware detection tool that provides additional description tags useful for remediation. Moreover, potentially, if the corresponding evaluation results allow it, it could also be used to provide information about the malware family each analysed sample most probably belongs to, among the set of families of interest.

This thesis focuses on the first three phases previously mentioned. In particular, it concentrates on defining, training and evaluating the best model architecture possible for the tasks at hand. However, some code optimization challenges resulting from the slowness of the code in the instance used for the experiments meant that it could be possible to train the model only with the first half of the samples of the Sorel20M dataset in a reasonable time, with some approximations on the samples dispersion when random sampling them from the dataset. This resulted in slightly worse performance than might be expected using the current architecture with the entire dataset. Nevertheless, the deployment of the proposed <b>MTJE</b> model on a real-world scenario is theoretically possible with the current final architecture, although it would be better to train the model on the whole Sorel20M dataset on a better instance first in order to see its true potential.

At a later moment, the proposed framework was extended with the addition of a <b>Malware Family Classifier</b> model head defined on top of the proposed <b>MTJE</b> model base topology in order to improve its relatively poor results in the <b>Malware family prediction/classification</b> task. This new model was then specifically trained (and tested) for such purpose using the training and test subsets of the relatively small <b>Fresh Dataset</b>, which contain the information about the malware family each sample belongs to. However, instead of training the newly defined architecture from scratch on such small dataset at the risk of overfitting, the technique called <b>Transfer Learning</b> was used by transferring the knowledge (the learned model parameters) from a previous <b>MTJE</b> model training run on the large Sorel20M dataset onto the new model base topology (the one shared with the <b>MTJE</b> model architecture), before training. Then, during the training procedure, some of the imported parameters were 'fine-tuned' while the ones corresponding to the newly added <b>Family Classifier</b> head were learned from scratch.

However, this new <b>Family Classifier</b> model could not be used to produce family rankings nor to query samples based on their similarity to some anchor, which are very useful tasks in the field of Information Security since they allow to quickly obtain samples similar to the currently analysed one, facilitating its study. Moreover, this model was also limited to working only with a fixed number of predefined families. Therefore, in order to overcome such limitations a new model - referred to as <b>Contrastive Model</b> - was introduced consisting of a <b>Siamese Network</b> which refined, in a contrastive learning setting, the implicit representation of PE files (PE Embeddings) learned by a previous <b>MTJE</b> model training run on the Sorel20M dataset (with the aid of Transfer Learning) using samples from the training subset of the fresh dataset with the <b>Online Triplet Loss</b> function. The learned PE Embeddings can, in fact, be used to address both the <b>family prediction/classification</b> – applying the distance weighted k-NN (k Nearest Neighbours) algorithm in the resulting embedding space - and <b>ranking</b> tasks and to query samples based on their similarity in the Embedding space.

The current implementation of the <b>MTJE</b> model provided very good results in the tasks of <b>Malware detection</b> and <b>Malware description via SMART tags</b>, considering the number of samples it was trained on. Moreover, the <b>Family Classifier</b> and the <b>Contrastive Model</b> performed relatively well on the <b>Malware Family Classification</b> and <b>Ranking</b> (when possible) tasks considering the small and low quality dataset (fresh dataset) they were trained on. However, these models have also some limitations, such as the results in the <b>family classification</b> and <b>ranking</b> tasks which could be much better if a bigger and higher quality dataset was used during training, and the lack of interpretability of the resulting implicit signatures. Future works capable of overcoming these shortcomings may be extremely helpful to malware analysts, antivirus software developers and system administrators and could even enable the generation of explicit (and thus more interpretable) signatures derived from the learned implicit ones.

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
1. Section `general`
   - `device`: desired device to train the model on, e.g. 'cuda:0' if a GPU is available, otherwise 'cpu'
   - `workers`: number of workers to be used (if 0 -> set to current system cpu count)
   - `runs`: number of training runs to do


2. Section `sorel20mDataset`
   - `training_n_samples`: max number of training data samples to use (if -1 -> takes all)
   - `validation_n_samples`: max number of validation data samples to use (if -1 -> takes all)
   - `test_n_samples`: max number of test data samples to use (if -1 -> takes all)
   - `validation_test_split`: (should not be changed) timestamp that divides the validation data (used to check convergence/overfitting) from test data (used to assess final performance)
   - `train_validation_split`: (should not be changed) timestamp that splits training data from validation data
   - `total_training_samples`: (should not be changed) total number of available training samples in the original Sorel20M dataset
   - `total_validation_samples`: (should not be changed) total number of available validation samples in the original Sorel20M dataset
   - `total_test_samples`: (should not be changed) total number of available test samples in the original Sorel20M dataset


3. Section `aloha`
   - `batch_size`: how many samples per batch to load
   - `epochs`: how many epochs to train for
   - `use_malicious_labels`: whether or not (1/0) to use malware/benignware labels as a target
   - `use_count_labels`: whether or not (1/0) to use the counts as an additional target
   - `use_tag_labels`: whether or not (1/0) to use the tags as additional targets
   - `layer_sizes`: define detectionBase net initial linear layers sizes (and amount). Examples:
      - `[512,512,128]`: the initial layers (before the task branches) will be 3 with sizes 512, 512, 128 respectively
      - `[512,256]`: the initial layers (before the task branches) will be 2 with sizes 512, 256 respectively
   - `dropout_p`: dropout probability between the first detectionBase net layers
   - `activation_function`: activation function between the first aloha net layers. Possible values:
      - `elu`: Exponential Linear Unit activation function
      - `leakyRelu`: leaky Relu activation function
      - `pRelu`: parametric Relu activation function (better to use this with weight decay = 0)
      - `relu`: Rectified Linear Unit activation function
   - `normalization_function`: normalization function between the first aloha net layers. Possible values:
      - `layer_norm`: the torch.nn.LayerNorm function
      - `batch_norm`: the torch.nn.BatchNorm1d function
   - `loss_weights`: label weights to be used during loss calculation (Notice: only the weights corresponding to enabled labels will be used). Example: `{'malware': 1.0, 'count': 0.1, 'tags': 1.0}`
   - `optimizer`: optimizer to use during training. Possible values:
      - `adam`: Adam algorithm
      - `sgd`: stochastic gradient descent
   - `lr`: learning rate to use during training
   - `momentum`: momentum to be used during training when using 'sgd' optimizer
   - `weight_decay`: weight decay (L2 penalty) to use with selected optimizer
   - `gen_type`: generator type. Possible values are:
      - `base`: use basic generator (from the original SOREL20M code) modified to work with the pre-processed dataset
      - `alt1`: use alternative generator 1. Inspired by the 'index select' version of https://discuss.pytorch.org/t/dataloader-much-slower-than-manual-batching/27014/6, this version uses a new dataloader class, called FastTensorDataloader, to process tabular based data. It was modified from the original version available at the above link to be able to work with the pre-processed dataset (numpy memmap) and with multiple workers (in multiprocessing)
      - `alt2`: use alternative generator 2. Inspired by the 'shuffle in-place' version of https://discuss.pytorch.org/t/dataloader-much-slower-than-manual-batching/27014/6, this version uses a new dataloader class, called FastTensorDataloader, to process tabular based data. It was modified from the original version available at the above link to be able to work with the pre-processed dataset (numpy memmap) and with multiple workers (in multiprocessing)
      - `alt3`: use alternative generator 3. This version uses a new dataloader class, called FastTensorDataloader which asynchronously (if workers > 1) loads the dataset into memory in randomly chosen chunks which are concatenated together to form a 'chunk aggregate' -> the data inside a chunk aggregate is then shuffled. Finally batches of data are extracted from a chunk aggregate. The samples shuffling is therefore more localised but the loading speed is greatly increased
   

4. Section `mtje`
   - `batch_size`: how many samples per batch to load
   - `epochs`: how many epochs to train for
   - `use_malicious_labels`: whether or not (1/0) to use malware/benignware labels as a target
   - `use_count_labels`: whether or not (1/0) to use the counts as an additional target
   - `layer_sizes`: define mtje net initial linear layers sizes (and amount). Examples:
      - `[512,512,128]`: the initial layers (before the task branches) will be 3 with sizes 512, 512, 128 respectively
      - `[512,256]`: the initial layers (before the task branches) will be 2 with sizes 512, 256 respectively
   - `dropout_p`: dropout probability between the first mtje net layers
   - `activation_function`: activation function between the first aloha net layers. Possible values:
      - `elu`: Exponential Linear Unit activation function
      - `leakyRelu`: leaky Relu activation function
      - `pRelu`: parametric Relu activation function (better to use this with weight decay = 0)
      - `relu`: Rectified Linear Unit activation function
   - `normalization_function`: normalization function between the first aloha net layers. Possible values:
      - `layer_norm`: the torch.nn.LayerNorm function
      - `batch_norm`: the torch.nn.BatchNorm1d function
   - `loss_weights`: label weights to be used during loss calculation (Notice: only the weights corresponding to enabled labels will be used). Example: `{'malware': 1.0, 'count': 0.1, 'tags': 1.0}`
   - `optimizer`: optimizer to use during training. Possible values:
      - `adam`: Adam algorithm
      - `sgd`: stochastic gradient descent
   - `lr`: learning rate to use during training
   - `momentum`: momentum to be used during training when using 'sgd' optimizer
   - `weight_decay`: weight decay (L2 penalty) to use with selected optimizer
   - `gen_type`: generator type. Possible values are:
       - `base`: use basic generator (from the original SOREL20M code) modified to work with the pre-processed dataset
       - `alt1`: use alternative generator 1. Inspired by the 'index select' version of https://discuss.pytorch.org/t/dataloader-much-slower-than-manual-batching/27014/6, this version uses a new dataloader class, called FastTensorDataloader, to process tabular based data. It was modified from the original version available at the above link to be able to work with the pre-processed dataset (numpy memmap) and with multiple workers (in multiprocessing)
       - `alt2`: use alternative generator 2. Inspired by the 'shuffle in-place' version of https://discuss.pytorch.org/t/dataloader-much-slower-than-manual-batching/27014/6, this version uses a new dataloader class, called FastTensorDataloader, to process tabular based data. It was modified from the original version available at the above link to be able to work with the pre-processed dataset (numpy memmap) and with multiple workers (in multiprocessing)
       - `alt3`: use alternative generator 3. This version uses a new dataloader class, called FastTensorDataloader which asynchronously (if workers > 1) loads the dataset into memory in randomly chosen chunks which are concatenated together to form a 'chunk aggregate' -> the data inside a chunk aggregate is then shuffled. Finally batches of data are extracted from a chunk aggregate. The samples shuffling is therefore more localised but the loading speed is greatly increased
   - `similarity_measure`: similarity measure used to evaluate distances in joint embedding space. Possible values are:
      - `dot`: dot product between vectors in the embedding space. The similarity measure used in JointEmbedding paper
      - `cosine`: cosine similarity between vectors in the embedding space
      - `pairwise_distance`: calculates the pairwise distance and then transforms it to a similarity measure (between 0 and 1)
   - `pairwise_distance_to_similarity_function`: (IF 'pairwise_distance' IS SELECTED AS similarity_measure) - distance-to-similarity function to use. These functions will map values belonging to the R+ set (Real positives) to real values belonging to the [0,1] interval. Possible values are:
      - `exp`: will compute e^(-x/a)
      - `inv`: will compute 1/(1+x/a)
      - `inv_pow`: will compute 1/(1+(x^2)/a)
   
      where 'a' is a multiplicative factor (see 'pairwise_a')
   - `pairwise_a`: (IF 'pairwise_distance' IS SELECTED AS similarity_measure) - distance-to-similarity function 'a' multiplicative factor


5. Section `freshDataset`:
   - `families`: malware Bazaar families of interest. NOTE: It is recommended to specify more families than 'number_of_families' since Malware Bazaar may not have 'amount_each' samples for some of them. These families will be considered in order.
   - `number_of_families`: number of families to consider. The ones in excess, going in order, will not be considered.
   - `amount_each`: amount of samples for each malware family to retrieve from Malware Bazaar
   - `n_queries`: number of query samples per-family to consider
   - `min_n_anchor_samples`: minimum number of anchor samples to use, per-family
   - `max_n_anchor_samples`: maximum number of anchor samples to use, per-family
   - `n_evaluations`: number of evaluations to perform (for uncertainty estimates)


6. Section `familyClassifier`:
   - `epochs`: how many epochs to train the family classifier for
   - `train_split_proportion`: proportion of the whole fresh dataset to use for training the family classifier
   - `valid_split_proportion`: proportion of the whole fresh dataset to use for validating the family classifier
   - `test_split_proportion`: proportion of the whole fresh dataset to use for testing the family classifier
   - `batch_size`: how many samples per batch to load for the family classifier
   - `optimizer`: optimizer to use during training. Possible values:
      - `adam`: Adam algorithm
      - `sgd`: stochastic gradient descent
   - `lr`: learning rate to use during training
   - `momentum`: momentum to be used during training when using 'sgd' optimizer
   - `weight_decay`: weight decay (L2 penalty) to use with selected optimizer
   - `layer_sizes`: define family classifier output head size and number of linear layers. Examples:
     - `[128,256,64]`: the family classifier layers will be 3 with sizes 128, 256, 64 respectively
     - `[128,64]`: the family classifier layers will be 2 with sizes 128, 64 respectively


7. Section `contrastiveLearning`:
   - `epochs`: how many epochs to train the contrastive model for
   - `train_split_proportion`: proportion of the whole fresh dataset to use for training the contrastive model
   - `valid_split_proportion`: proportion of the whole fresh dataset to use for validating the contrastive model
   - `test_split_proportion`: proportion of the whole fresh dataset to use for testing the contrastive model
   - `batch_size`:  how many samples per batch to load for the contrastive model
   - `optimizer`: optimizer to use during training. Possible values:
      - `adam`: Adam algorithm
      - `sgd`: stochastic gradient descent
   - `lr`: learning rate to use during training
   - `momentum`: momentum to be used during training when using 'sgd' optimizer
   - `weight_decay`: weight decay (L2 penalty) to use with selected optimizer
   - `hard`: online triplet mining function to use when training the model with contrastive learning. Possible values:
     - `0`: batch_all_triplet_loss online triplet mining function
     - `1`: batch_hard_triplet_loss online triplet mining function
   - `margin`: margin to use in the triplet loss
   - `squared`: whether (1) to use the squared euclidean norm as distance metric or the simple euclidean norm (0)
   - `rank_size`: size of the produced rankings
   - `knn_k_min`: minimum number of nearest neighbours to consider when classifying samples with k-NN algorithm (only odd numbers between knn_k_min and knn_k_max, included, will be used)
   - `knn_k_max`: maximum number of nearest neighbours to consider when classifying samples with k-NN algorithm (only odd numbers between knn_k_min and knn_k_max, included, will be used)

## Joint Embedding Workflow (main)

Command used to activate an entire Automatic Malware Signature Generation MLflow workflow using values set in <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#config-file' title='config file'>config file</a>.
In particular the workflow is composed of the following steps:
1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#dataset-download' title='Dataset Download'>Dataset Download</a> (if both the pre-processed and the original SOREL20M dataset are not present on disk)
1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#pre-process-dataset' title='Pre-Process Dataset'>Pre-Process Dataset</a> (if the pre-processed dataset is not present on disk)
1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#build-fresh-dataset' title='Build Fresh Dataset'>Build Fresh Dataset</a> (if the fresh dataset is not present on disk)
1. For 'runs' (configurable in <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#config-file' title='config file'>config file</a>) times:
    1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#train-network' title='Train Network'>Train Network</a>
    1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#evaluate-network' title='Evaluate Network'>Evaluate Network</a>
    1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#compute-all-run-results' title='Compute All Run Results'>Compute All Run Results</a>
    1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#evaluate-fresh' title='Evaluate Fresh'>Evaluate Fresh</a>
    1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#compute-all-run-fresh-results' title='Compute All Run Fresh Results'>Compute All Run Fresh Results</a>
1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#plot-all-roc-distributions' title='Plot All ROC Distributions'>Plot All ROC Distributions</a>
1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#plot-all-fresh-roc-distributions' title='Plot All Fresh ROC Distributions'>Plot All Fresh ROC Distributions</a>
    
```
mlflow run /path/to/Automatic-Malware-Signature-Generation \
-P base_dir=<tool destination dir> \
-P use_cache=<whether to skip already executed runs (in cache) or not (1/0). (default: 1)> \
-P ignore_git=<whether to ignore git version or not (1/0)(default: 0)>
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
    1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#compute-all-run-results' title='Compute All Run Results'>Compute All Run Results</a>
1. <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation#plot-all-roc-distributions' title='Plot All ROC Distributions'>Plot All ROC Distributions</a>
```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e detection_workflow \
-P base_dir=<tool destination dir> \
-P use_cache=<whether to skip already executed runs (in cache) or not (1/0) (default: 1)> \
-P ignore_git=<whether to ignore git version or not (1/0) (default: 0)>
```

---
# How to Run - Single steps
## Dataset Download

Command used to download SOREL20M dataset elements from the s3 socket and save them in the specified destination directory on the current machine.
```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e download_dataset \
-P destination_dir=<path to the destination folder where to save the element to>
```

---
## Pre-process Dataset
### Pre-process Dataset

Command used to pre-process SOREL20M dataset transforming it to a more easy (and quick) to read dataset format.
```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e preprocess_dataset \
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
mlflow run /path/to/Automatic-Malware-Signature-Generation -e preprocess_ds_multi \
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
mlflow run /path/to/Automatic-Malware-Signature-Generation -e combine_ds_files \
-P ds_path=<local_multi_path> \
-P training_n_samples=<max number of training data samples to use (if -1 -> takes all) (default: -1)> \
-P validation_n_samples=<max number of validation data samples to use (if -1 -> takes all) (default: -1)> \
-P test_n_samples=<max number of test data samples to use (if -1 -> takes all) (default: -1)>
```

---
## Train Network

Command used to train the (chosen) feed-forward neural network on EMBER 2.0 features, optionally with additional targets as described in the ALOHA paper (https://arxiv.org/abs/1903.05700). SMART tags based on (https://arxiv.org/abs/1905.06262).
```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e train_network \
-P ds_path=<path of the directory where to find the pre-processed dataset (containing .dat files)> \
-P net_type=<network to use between 'JointEmbedding', 'JointEmbedding_cosine', 'JointEmbedding_pairwise_distance' and 'DetectionBase' (default: jointEmbedding)> \
-P gen_type=<generator (and dataset) class to use between 'base', 'alt1', 'alt2', 'alt3' (default: base)> \
-P run_id=<mlflow run id of a previously stopped run to resume (default: 0)> \
-P training_run=<training run identifier (default: 0)> \
-P batch_size=<how many samples per batch to load (default: 8192)> \
-P epochs=<how many epochs to train for (default: 10)> \
-P training_n_samples=<number of training samples to consider (0 -> take all) (default: 0)> \
-P validation_n_samples=<number of validation samples to consider (0 -> take all) (default: 0)> \
-P use_malicious_labels=<whether or not (1/0) to use malware/benignware labels as a target (default: 1)> \
-P use_count_labels=<whether or not (1/0) to use the counts as an additional target (default: 1)> \
-P use_tag_labels=<whether or not (1/0) to use the tags as additional targets (default: 1)> \
-P workers=<how many worker (threads) should the dataloader use (default: 0 -> use multiprocessing.cpu_count())>
```

---
## Evaluate Network

Command used to produce and output (to a csv file) evaluation results for a trained feedforward neural network model.
```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e evaluate_network \
-P ds_path=<path of the directory where to find the pre-processed dataset (containing .dat files)> \
-P checkpoint_file=<path to the model checkpoint to load> \
-P net_type=<network to use between 'JointEmbedding', 'JointEmbedding_cosine', 'JointEmbedding_pairwise_distance' and 'DetectionBase' (default: jointEmbedding)> \
-P gen_type=<generator (and dataset) class to use between 'base', 'alt1', 'alt2', 'alt3' (default: base)> \
-P batch_size=<how many samples per batch to load (default: 10)> \
-P test_n_samples=<number of test samples to consider (0 -> take all) (default: 0)> \
-P evaluate_malware=<whether or not (1/0) to record malware labels and predictions (default: 1)> \
-P evaluate_count=<whether or not (1/0) to record count labels and predictions (default: 1)> \
-P evaluate_tags=<whether or not (1/0) to use SMART tags as additional targets (default: 1)>
```

---
## Compute All Run Results

Command used to compute and plot all the per-tag and mean per-sample scores for a single model training run.
```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e compute_all_run_results \
-P results_file=<path to results.csv containing the output of a model run> \
-P use_malicious_labels=<whether or not (1/0) to compute malware/benignware label scores (default: 1)> \
-P use_tag_labels=<whether or not (1/0) to compute the tag label scores (default: 1)>
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
mlflow run /path/to/Automatic-Malware-Signature-Generation -e plot_all_roc_distributions \
-P run_to_filename_json=<path to the run_to_filename_json file> \
-P use_malicious_labels=<whether or not (1/0) to compute malware/benignware label scores (default: 1)> \ 
-P use_tag_labels=<whether or not (1/0) to compute the tag label scores (default: 1)>
```

---
## Build Fresh Dataset

Command used to build a 'fresh' dataset retrieving samples from Malware Bazaar given a list of malware families stored in a configuration file.
```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e build_fresh_dataset \
-P dataset_dest_dir=<dir where to write the newly created dataset>
```

---
## Evaluate Fresh

Command used to produce and output (to a json file and a bunch of csv files) fresh dataset evaluation prediction and ranking results for a trained feedforward neural network model.
```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e evaluate_fresh \
-P ds_path=<path of the directory where to find the fresh dataset (containing .dat files)> \
-P checkpoint_path=<path to the model checkpoint to load> \
-P net_type=<network to use between 'JointEmbedding', 'JointEmbedding_cosine', 'JointEmbedding_pairwise_distance' and 'DetectionBase' (default: jointEmbedding)> \
-P n_anchor_samples_per_family=<number of anchor samples per-family to use during prediction evaluation (default: 10)>
-P hard=<whether to perform a 'hard' (1) or 'soft' (0) malware family prediction (default: 0)>
-P n_queries=<number of queries to do during ranking evaluation (default: 100)>
```

---
### Compute All Run Fresh Results
Command used to compute and plot all the per-family and mean per-sample scores for a single model evaluation on the fresh dataset.
```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e compute_all_run_results \
-P results_file=<path to results.csv containing the output of a model run> \
-P ds_path=<fresh dataset root directory (where to find .dat files)>
```

---
## Plot All Fresh ROC Distributions

Command used to compute the mean and standard deviation of the TPR at a range of FPRS (the ROC curve) over several sets of evaluation results on the fresh dataset (at least 2 runs) for a given family.
The run_to_filename_json file must have the following format:
```
{"run_id_0": "/full/path/to/results.csv/for/run/0/fresh_results.csv",
 "run_id_1": "/full/path/to/results.csv/for/run/1/fresh_results.csv",
  ...
}
```
```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e plot_all_fresh_roc_distributions \
-P run_to_filename_json=<path to the run_to_filename_json file> \
-P ds_path=<fresh dataset root directory (where to find .dat files)>
```

---
## Generator alt3 speed evaluation
Selecting different values for chunk_size and n_chunks has an impact on the speed of the generator alt3 and on the samples dispersion.
To select good values for chunk_size and n_chunks for your system you can use the combination of the following two commands which evaluates the generator alt3 speed on the target machine.
These functions will perform 'epochs' model training epochs using values for chunk_size and n_chunks got from two intervals and will plot 2 heatmaps: the first containing the average elapsed times and the second the average speeds.
When making the final decision on the aforementioned values it is better to consider a higher value for n_chunks in order to increase samples dispersion during shuffling.
The default values of `CHUNK_SIZE=256` and `CHUNKS=256` are hardcoded in the `generators_alt3.py` file. These should be good values in most cases. If you want to change them hardcode the new values in the code.

### Evaluate gen3 speed

Command used to evaluate generator alt3 speed changing values for 'chunk_size' and 'chunks' variables. The evaluation is done the number of epochs specified for each combination of values and the results averaged. The resulting elapsed times and speeds are save to a json file.
```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e evaluate_gen3_speed \
-P ds_path=<path of the directory where to find the fresh dataset (containing .dat files)> \
-P json_file_path=<Path to a new or an existent (from a previous run) json file to be used to store run evaluation elapsed times and speeds> \
-P net_type=<network to use between 'JointEmbedding', 'JointEmbedding_cosine', 'JointEmbedding_pairwise_distance' and 'DetectionBase' (default: jointEmbedding)> \
-P batch_size=<How many samples per batch to load. (default: 8192)> \
-P min_mul=<Minimum product between chunks and chunk_size to consider (in # of batches). (default: 1)> \
-P max_mul=<Maximum product between chunks and chunk_size to consider (in # of batches). (default: 32)> \
-P epochs=<How many epochs to train for. (default: 1)> \
-P training_n_samples=<Number of training samples to consider (used to access the right files). (default: 0 -> all)> \
-P use_malicious_labels=<Whether or (1/0) not to use malware/benignware labels as a target. (default: 1)> \
-P use_count_labels=<Whether or not (1/0) to use the counts as an additional target. (default: 1)> \
-P use_tag_labels=<Whether or not (1/0) to use the tags as additional targets. (default: 1)> \
-P workers=<How many worker (threads) should the dataloader use (default: 0 -> use multiprocessing.cpu_count())>
```

---
### Create gen3 heatmap

Command used to produce elapsed times and speeds heatmaps from the json file resulting from 'gen3_eval', which contains the times elapsed and speeds for a number of evaluation runs.
```
mlflow run /path/to/Automatic-Malware-Signature-Generation -e create_gen3_heatmap \
-P json_file_path=<Path the json file containing the run evaluation elapsed times and speeds>
```

---

# Wiki
There is now a <a href='https://github.com/cmikke97/Automatic-Malware-Signature-Generation/wiki' title='Wiki!'>📖wiki</a>!

---

# Copyright and License

Copyright 2021 Crepaldi Michele

Developed as a thesis project at the TORSEC research group of the Polytechnic of Turin (Italy) under the supervision of professor Antonio Lioy and engineer Andrea Atzeni and with the support of engineer Andrea Marcelli.


Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License. You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.