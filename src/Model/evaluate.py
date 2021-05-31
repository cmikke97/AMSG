import configparser  # implements a basic configuration language for Python programs
import importlib  # provides the implementation of the import statement in Python source code
import os  # provides a portable way of using operating system dependent functionality
import tempfile  # used to create temporary files and directories

import baker  # easy, powerful access to Python functions from the command line
import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
import pandas as pd  # pandas is a flexible and easy to use open source data analysis and manipulation tool
import torch  # tensor library like NumPy, with strong GPU support
import tqdm  # instantly makes loops show a smart progress meter
from logzero import logger  # robust and effective logging for Python


def import_modules(net_type,  # network type (possible values: jointEmbedding, detectionBase)
                   gen_type):  # generator type (possible values: base, alt1, alt2)
    """ Dynamically import network, dataset and generator modules depending on the provided arguments.

    Args:
        net_type: Network type (possible values: jointEmbedding, detectionBase)
        gen_type: Generator type (possible values: base, alt1, alt2)
    Returns:
        Net, normalize_results, Dataset, get_generator, device imported from selected modules.
    """

    # set network module name based on the current network type
    if net_type.lower() == 'jointembedding':
        net_type = 'jointEmbedding'
        net_module_name = "nets.JointEmbedding_net"
    elif net_type.lower() == 'detectionbase':
        net_type = 'detectionBase'
        net_module_name = "nets.DetectionBase_net"
    else:  # if the network type is neither JointEmbedding nor DetectionBase raise ValueError
        raise ValueError('Unknown Network type. Possible values: "JointEmbedding", "DetectionBase". Got {}'
                         .format(net_type))

    gen_type = gen_type.lower()

    # set dataset and generator module names based on the current generator type
    if gen_type == 'base':
        ds_module_name = "nets.generators.dataset"
        gen_module_name = "nets.generators.generators"
    elif gen_type == 'alt1':
        ds_module_name = "nets.generators.dataset_alt"
        gen_module_name = "nets.generators.generators_alt1"
    elif gen_type == 'alt2':
        ds_module_name = "nets.generators.dataset_alt"
        gen_module_name = "nets.generators.generators_alt2"
    else:  # if the generator type is neither base, nor alt1, nor alt2 raise ValueError
        raise ValueError('Unknown Generator type. Possible values: "base", "alt1", "alt2". Got {}'
                         .format(net_type))

    # import net module
    net_module = importlib.import_module(net_module_name)
    # get 'Net' class from net module
    Net = getattr(net_module, 'Net')
    # get 'normalize_results' function from net module
    normalize_results = getattr(net_module, 'normalize_results')

    # get dataset and generator modules
    ds_module = importlib.import_module(ds_module_name)
    gen_module = importlib.import_module(gen_module_name)
    # get 'Dataset' class from ds module
    Dataset = getattr(ds_module, 'Dataset')
    # get 'get_generator' function from gen module
    get_generator = getattr(gen_module, 'get_generator')

    # get config file path
    model_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.dirname(model_dir)
    config_filepath = os.path.join(src_dir, 'config.ini')

    # instantiate config parser and read config file
    config = configparser.ConfigParser()
    config.read(config_filepath)

    # get variables from config file (the section depends on the net type)
    device = config[net_type]['device']

    # return classes, functions and variables imported
    return Net, normalize_results, Dataset, get_generator, device


@baker.command
def evaluate_network(ds_path,  # path of the directory where to find the pre-processed dataset (containing .dat files)
                     checkpoint_file,  # the checkpoint file containing the weights to evaluate
                     net_type='JointEmbedding',  # network to use between 'JointEmbedding' and 'DetectionBase'
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
        evaluate_malware: Whether (1/0) to record malware labels and predictions (default: 1)
        evaluate_count: Whether (1/0) to record count labels and predictions (default: 1)
        evaluate_tags: Whether (1/0) to use SMART tags as additional targets (default: 1).
        feature_dimension: The input dimension of the model
    """

    ds_path = os.path.normpath(ds_path)

    # dynamically import some classes, functions and variables from modules depending on the current net and gen types
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

        # create temporary directory
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
