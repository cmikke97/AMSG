import configparser  # implements a basic configuration language for Python programs
import json  # json encoder and decoder
import os  # provides a portable way of using operating system dependent functionality
import sys  # system-specific parameters and functions
import tempfile  # used to create temporary files and directories
import time  # provides various time-related functions
from copy import deepcopy  # creates a new object and recursively copies the original object elements

import baker  # easy, powerful access to Python functions from the command line
import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
import numpy as np  # the fundamental package for scientific computing with Python
import pandas as pd  # pandas is a flexible and easy to use open source data analysis and manipulation tool
import psutil  # used for retrieving information on running processes and system utilization
import torch  # tensor library like NumPy, with strong GPU support
from logzero import logger  # robust and effective logging for Python

from nets.Family_classification_net import Net as Family_Net
from nets.generators.fresh_generators import get_generator

# get config file path
model_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(model_dir)
config_filepath = os.path.join(src_dir, 'config.ini')

# instantiate config parser and read config file
config = configparser.ConfigParser()
config.read(config_filepath)

# get variables from config file
device = config['general']['device']

try:
    # try getting layer sizes from config file
    layer_sizes = json.loads(config['jointEmbedding']['layer_sizes'])
except json.JSONDecodeError:
    # if the option is not present in the config file set layer sizes to None
    layer_sizes = None

try:
    # try getting layer sizes from config file
    fam_class_layer_sizes = json.loads(config['familyClassifier']['layer_sizes'])
except json.JSONDecodeError:
    # if the option is not present in the config file set layer sizes to None
    fam_class_layer_sizes = None

# instantiate run additional parameters dict setting values got from config file
run_additional_params = {
    'layer_sizes': layer_sizes,
    'dropout_p': float(config['jointEmbedding']['dropout_p']),
    'activation_function': config['jointEmbedding']['activation_function'],
    'optimizer': config['familyClassifier']['optimizer'],
    'lr': float(config['familyClassifier']['lr']),
    'momentum': float(config['familyClassifier']['momentum']),
    'weight_decay': float(config['familyClassifier']['weight_decay']),
    'fam_class_layer_sizes': fam_class_layer_sizes
}


@baker.command
def evaluate_network(fresh_ds_path,  # path of the directory where to find the fresh dataset (containing .dat files)
                     checkpoint_path,  # path to the model checkpoint to load
                     training_run=0,  # training run identifier
                     train_split_proportion=8,
                     valid_split_proportion=1,
                     test_split_proportion=1,
                     batch_size=250,  # how many samples per batch to load
                     # if provided, seed random number generation with this value (defaults None, no seeding)
                     random_seed=None,
                     # how many worker (threads) the dataloader uses (default: 0 -> use multiprocessing.cpu_count())
                     workers=0):
    # start mlflow run
    with mlflow.start_run() as mlrun:
        if train_split_proportion <= 0 or valid_split_proportion <= 0 or test_split_proportion <= 0:
            raise ValueError('train, valid and test split proportions must be positive integers.')

        dataset_split_proportions = [train_split_proportion, valid_split_proportion, test_split_proportion]

        # if workers has a value (it is not None) then convert it to int if it is > 0, otherwise set it to None
        workers = workers if workers is None else int(workers) if int(workers) > 0 else None

        if random_seed is not None:  # if a seed was provided
            logger.info(f"Setting random seed to {int(random_seed)}.")
            # set the seed for generating random numbers
            torch.manual_seed(int(random_seed))

        logger.info('...instantiating family classifier network for evaluation run n. {}'.format(training_run))

        # create fresh dataset generator
        _, _, test_generator = get_generator(ds_root=fresh_ds_path,
                                             splits=dataset_split_proportions,
                                             batch_size=batch_size,
                                             return_shas=True,
                                             num_workers=workers,
                                             shuffle=True)  # shuffle samples

        # get label to signature function from the dataset (used to convert numerical labels to family names)
        label_to_sig = test_generator.dataset.label_to_sig

        n_families = test_generator.dataset.n_families

        # create JointEmbeddingNet model
        model = Family_Net(families=[label_to_sig(lab) for lab in range(n_families)],
                           feature_dimension=2381,
                           embedding_dimension=32,
                           layer_sizes=run_additional_params['layer_sizes'],
                           fam_class_layer_sizes=run_additional_params['fam_class_layer_sizes'],
                           dropout_p=run_additional_params['dropout_p'],
                           activation_function=run_additional_params['activation_function'])

        model.load_state_dict(torch.load(checkpoint_path))

        # allocate model to selected device (CPU or GPU)
        model.to(device)

        logger.info('Evaluating family classifier model..')
        model.eval()

        # get number of steps per epoch (# of total batches) from generator
        steps_per_epoch = len(test_generator)

        # create temporary directory
        with tempfile.TemporaryDirectory() as tempdir:
            filename = os.path.join(tempdir, 'results.csv')

            # create and open the results file in write mode
            with open(filename, 'w') as f:
                first_batch = True

                accuracy_history = []
                # set current validation step start time
                start_time = time.time()

                # for all the batches in the generator (Dataloader)
                for i, (shas, features, labels) in enumerate(test_generator):
                    shas = np.asarray(shas)
                    features = deepcopy(features).to(device)
                    labels = deepcopy(labels.long()).to(device)

                    # perform a forward pass through the network and get predictions
                    out = model(features)

                    # get predictions
                    _, preds = torch.max(out['scores'], 1)
                    accuracy = torch.sum(torch.eq(preds, labels).long()).item() / labels.size(0)

                    accuracy_history.append(accuracy)
                    # Calculate mean accuracy
                    mean_accuracy = np.mean(accuracy_history)

                    # compute current validation step elapsed time (in seconds)
                    elapsed_time = time.time() - start_time

                    # create loss string with the current loss
                    acc_str = 'Family prediction accuracy: {:7.3f}'.format(accuracy)
                    acc_str += ' | mean accuracy: {:7.3f}'.format(mean_accuracy)

                    # write on standard out the loss string + other information (elapsed time, predicted total
                    # validation completion time, current mean speed and main memory usage)
                    sys.stdout.write('\r Family classifier model eval: {}/{} '.format(i + 1, steps_per_epoch)
                                     + '[{}/{}, {:6.3f}it/s, RAM used: {:4.1f}%] '
                                     .format(time.strftime("%H:%M:%S", time.gmtime(elapsed_time)),  # show elapsed time
                                             time.strftime("%H:%M:%S",  # predict total validation completion time
                                                           time.gmtime(steps_per_epoch * elapsed_time / (i + 1))),
                                             (i + 1) / elapsed_time,  # compute current mean speed (it/s)
                                             psutil.virtual_memory().percent)  # get percentage of main memory used
                                     + acc_str)  # append accuracy string

                    # normalize the results
                    results = model.normalize_results(labels, out['probs'])

                    results.update({'preds': Family_Net.detach_and_copy_array(preds)})

                    # store results into a pandas dataframe (indexed by the sha265 keys) and then save it as csv into
                    # file f (inserting the header only if this is the first batch in the loop)
                    pd.DataFrame(results, index=shas).to_csv(f, header=first_batch)

                    first_batch = False

                # flush standard output
                sys.stdout.flush()
                print()

                mlflow.log_metric("test_accuracy", float(np.mean(accuracy_history)), step=0)

            # log results file as artifact
            mlflow.log_artifact(filename, artifact_path="family_class_results")

        logger.info('...done')


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
