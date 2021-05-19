import configparser  # implements a basic configuration language for Python programs
import importlib
import os  # Provides a portable way of using operating system dependent functionality
# Used to construct a new compound object and then, recursively, insert copies into it of the objects
# found in the original
import tempfile  # used to create temporary files and directories

import baker  # Easy, powerful access to Python functions from the command line
import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
# Pandas is a fast, powerful, flexible and easy to use open source data analysis and manipulation tool
import pandas as pd  # Pandas is a flexible and easy to use open source data analysis and manipulation tool
import torch  # Tensor library like NumPy, with strong GPU support
import tqdm  # Instantly makes loops show a smart progress meter
from logzero import logger  # Robust and effective logging for Python


def import_modules(net_type, gen_type):
    if net_type.lower() == 'jointembedding':
        net_type = 'jointEmbedding'
        net_module_name = "utils.JointEmbedding_net"
    elif net_type.lower() == 'detectionbase':
        net_type = 'detectionBase'
        net_module_name = "utils.DetectionBase_net"
    else:
        raise ValueError('Unknown Network type. Possible values: "JointEmbedding", "DetectionBase". Got {}'
                         .format(net_type))

    gen_type = gen_type.lower()

    if gen_type == 'base':
        ds_module_name = "utils.dataset"
        gen_module_name = "utils.generators"
    elif gen_type == 'alt1':
        ds_module_name = "utils.dataset_alt"
        gen_module_name = "utils.generators_alt1"
    elif gen_type == 'alt2':
        ds_module_name = "utils.dataset_alt"
        gen_module_name = "utils.generators_alt2"
    else:
        raise ValueError('Unknown Generator type. Possible values: "base", "alt1", "alt2". Got {}'
                         .format(net_type))

    net_module = importlib.import_module(net_module_name)
    Net = getattr(net_module, 'Net')
    normalize_results = getattr(net_module, 'normalize_results')

    ds_module = importlib.import_module(ds_module_name)
    gen_module = importlib.import_module(gen_module_name)
    Dataset = getattr(ds_module, 'Dataset')
    get_generator = getattr(gen_module, 'get_generator')

    # get config file path
    model_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.dirname(model_dir)
    config_filepath = os.path.join(src_dir, 'config.ini')

    # instantiate config parser and read config file
    config = configparser.ConfigParser()
    config.read(config_filepath)

    # get variables from config file
    device = config[net_type]['device']

    return Net, normalize_results, Dataset, get_generator, device


@baker.command
def evaluate_network(ds_path,  # path of the directory where to find the pre-processed dataset (containing .dat files)
                     checkpoint_file,  # the checkpoint file containing the weights to evaluate
                     net_type='JointEmbedding',  # Network to use between 'JointEmbedding' and 'DetectionBase'
                     gen_type='base',  # generator (and dataset) class to use between 'base', 'alt1', 'alt2'
                     batch_size=8192,  # how many samples per batch to load
                     test_n_samples=-1,  # number of test samples to consider (used to access the right files)
                     evaluate_malware=1,  # whether or not to record malware labels and predictions
                     evaluate_count=1,  # whether or not to record count labels and predictions
                     evaluate_tags=1,  # whether or not to use SMART tags as additional targets
                     feature_dimension=2381):  # the input dimension of the model
    """ Take a trained feedforward neural network model and output evaluation results to a csv file.

    Args:
        ds_path: Path of the directory where to find the pre-processed dataset (containing .dat files)
        checkpoint_file: The checkpoint file containing the weights to evaluate
        net_type: Network to use between 'JointEmbedding' and 'DetectionBase'. (default: 'JointEmbedding')
        gen_type: Generator (and dataset) class to use between 'base', 'alt1', 'alt2'. (default: 'base')
        batch_size: How many samples per batch to load
        test_n_samples: Number of test samples to consider (used to access the right files)
        evaluate_malware: Whether or not (1/0) to record malware labels and predictions (default: 1)
        evaluate_count: Whether or not (1/0) to record count labels and predictions (default: 1)
        evaluate_tags: Whether or not (1/0) to use SMART tags as additional targets (default: 1).
        feature_dimension: The input dimension of the model
    """

    Net, normalize_results, Dataset, get_generator, device = import_modules(net_type=net_type,
                                                                            gen_type=gen_type)

    # start mlflow run
    with mlflow.start_run():
        if net_type == 'JointEmbedding':
            evaluate_tags = 1
        else:
            # check if at least one label type is active, otherwise error
            if not evaluate_malware and not evaluate_count and not evaluate_tags:
                raise ValueError("At least one between evaluate_malware, evaluate_count and evaluate_tags must be true")

        # create malware-NN model
        model = Net(use_malware=bool(evaluate_malware),
                    use_counts=bool(evaluate_count),
                    use_tags=bool(evaluate_tags),
                    n_tags=len(Dataset.tags),  # get n_tags counting tags from the dataset
                    feature_dimension=feature_dimension)

        # load model parameters from checkpoint
        model.load_state_dict(torch.load(checkpoint_file))

        # allocate model to selected device (CPU or GPU)
        model.to(device)

        # create test generator (a.k.a. test Dataloader)
        generator = get_generator(ds_root=ds_path,
                                  batch_size=batch_size,
                                  mode='test',  # select test mode
                                  n_samples=test_n_samples,
                                  use_malicious_labels=bool(evaluate_malware),
                                  use_count_labels=bool(evaluate_count),
                                  use_tag_labels=bool(evaluate_tags),
                                  return_shas=True)

        logger.info('...running network evaluation')

        with tempfile.TemporaryDirectory() as tempdir:
            filename = os.path.join(tempdir, 'results.csv')

            # create and open the results file in write mode
            with open(filename, 'w') as f:
                first_batch = True
                # for all the batches in the generator (Dataloader)
                for shas, features, labels in tqdm.tqdm(generator):
                    features = features.to(device)  # transfer features to selected device

                    # perform a forward pass through the network and get predictions
                    predictions = model(features)

                    # normalize the results
                    results = normalize_results(labels,
                                                predictions,
                                                use_malware=bool(evaluate_malware),
                                                use_count=bool(evaluate_count),
                                                use_tags=bool(evaluate_tags))

                    # store results into a pandas dataframe (indexed by the sha265 keys) and then save it as csv into
                    # file f (inserting the header only if this is the first batch in the loop)
                    pd.DataFrame(results, index=shas).to_csv(f, header=first_batch)

                    first_batch = False

            mlflow.log_artifact(filename, artifact_path="model_results")

        logger.info('...done')


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
