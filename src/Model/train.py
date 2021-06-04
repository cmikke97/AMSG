import configparser  # implements a basic configuration language for Python programs
import importlib  # provides the implementation of the import statement in Python source code
import os  # provides a portable way of using operating system dependent functionality
import shutil  # used to recursively copy an entire directory tree rooted at src to a directory named dst
import sys  # system-specific parameters and functions
from collections import defaultdict  # dict subclass that calls a factory function to supply missing values
from copy import deepcopy  # creates a new object and recursively copies the original object elements
from urllib import parse  # standard interface to break Uniform Resource Locator (URL) in components
import time

import baker  # easy, powerful access to Python functions from the command line
import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
import numpy as np  # the fundamental package for scientific computing with Python
import psutil
import torch  # tensor library like NumPy, with strong GPU support
from logzero import logger  # robust and effective logging for Python


def import_modules(net_type,  # network type (possible values: jointEmbedding, detectionBase)
                   gen_type):  # generator type (possible values: base, alt1, alt2)
    """ Dynamically import network, dataset and generator modules depending on the provided arguments.
    Args:
        net_type: Network type (possible values: jointEmbedding, detectionBase)
        gen_type: Generator type (possible values: base, alt1, alt2)
    Returns:
        Net, compute_loss, Dataset, get_generator, device imported from selected modules.
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
    elif gen_type == 'alt3':
        ds_module_name = "nets.generators.dataset_alt"
        gen_module_name = "nets.generators.generators_alt3"
    else:  # if the generator type is neither base, nor alt1, nor alt2 raise ValueError
        raise ValueError('Unknown Generator type. Possible values: "base", "alt1", "alt2", "alt3". Got {}'
                         .format(net_type))

    # import net module
    net_module = importlib.import_module(net_module_name)
    # get 'Net' class from net module
    Net = getattr(net_module, 'Net')
    # get 'compute_loss' function from net module
    compute_loss = getattr(net_module, 'compute_loss')

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
    return Net, compute_loss, Dataset, get_generator, device


@baker.command
def train_network(ds_path,  # path of the directory where to find the pre-processed dataset (containing .dat files)
                  net_type='JointEmbedding',  # network to use between 'JointEmbedding' and 'DetectionBase'
                  gen_type='base',  # generator (and dataset) class to use between 'base', 'alt1', 'alt2'
                  run_id=None,  # mlflow run id of a previously stopped run to resume
                  training_run=0,  # training run identifier
                  batch_size=8192,  # how many samples per batch to load
                  epochs=10,  # how many epochs to train for
                  training_n_samples=-1,  # number of training samples to consider (used to access the right files)
                  validation_n_samples=-1,  # number of validation samples to consider (used to access the right files)
                  use_malicious_labels=1,  # whether or not to use malware/benignware labels as a target
                  use_count_labels=1,  # whether or not to use the counts as an additional target
                  use_tag_labels=1,  # whether or not to use the tags as additional targets
                  feature_dimension=2381,  # The input dimension of the model
                  # if provided, seed random number generation with this value (defaults None, no seeding)
                  random_seed=None,
                  # How many worker processes should the dataloader use (if None use multiprocessing.cpu_count())
                  workers=-1):
    """ Train a feed-forward neural network on EMBER 2.0 features, optionally with additional targets as described in
    the ALOHA paper (https://arxiv.org/abs/1903.05700). SMART tags based on (https://arxiv.org/abs/1905.06262).
    Args:
        ds_path: Path of the directory where to find the pre-processed dataset (containing .dat files).
        net_type: Network to use between 'JointEmbedding' and 'DetectionBase'. (default: 'JointEmbedding')
        gen_type: Generator (and dataset) class to use between 'base', 'alt1', 'alt2'. (default: 'base')
        run_id: Mlflow run id of a previously stopped run to resume.
        training_run: Training run identifier. (default: 0) -> to plot base evaluation results with mean and confidence
                      we need at least 2 runs
        batch_size: How many samples per batch to load. (default: 8192)
        epochs: How many epochs to train for. (default: 10)
        training_n_samples: Number of training samples to consider (used to access the right files).
                            (default: -1 -> all)
        validation_n_samples: Number of validation samples to consider (used to access the right files).
                              (default: -1 -> all)
        use_malicious_labels: Whether or (1/0) not to use malware/benignware labels as a target. (default: 1)
        use_count_labels: Whether or not (1/0) to use the counts as an additional target. (default: 1)
        use_tag_labels: Whether or not (1/0) to use the tags as additional targets. (default: 1)
        feature_dimension: The input dimension of the model. (default: 2381 -> EMBER 2.0 feature size)
        random_seed: If provided, seed random number generation with this value. (default: None -> no seeding)
        workers: How many worker processes should the dataloader use (default: None -> use multiprocessing.cpu_count())
    """

    print('ds_path: {}'.format(ds_path))
    print('net_type: {}'.format(net_type))
    print('gen_type: {}'.format(gen_type))
    print('run_id: {}'.format(run_id))
    print('training_run: {}'.format(training_run))
    print('batch_size: {}'.format(batch_size))
    print('epochs: {}'.format(epochs))
    print('training_n_samples: {}'.format(training_n_samples))
    print('validation_n_samples: {}'.format(validation_n_samples))
    print('use_malicious_labels: {}'.format(use_malicious_labels))
    print('use_count_labels: {}'.format(use_count_labels))
    print('use_tag_labels: {}'.format(use_tag_labels))
    print('feature_dimension: {}'.format(feature_dimension))
    print('random_seed: {}'.format(random_seed))
    print('workers: {}'.format(workers))

    # dynamically import some classes, functions and variables from modules depending on the current net and gen types
    Net, compute_loss, Dataset, get_generator, device = import_modules(net_type=net_type,
                                                                       gen_type=gen_type)

    if run_id == '0':
        run_id = None

    # start mlflow run
    with mlflow.start_run() as mlrun:
        if net_type == 'JointEmbedding':
            use_tag_labels = 1

        # if workers has a value (it is not None) then convert it to int if it is > 0, otherwise set it to None
        workers = workers if workers is None else int(workers) if int(workers) > 0 else None

        if random_seed is not None:  # if a seed was provided
            logger.info(f"Setting random seed to {int(random_seed)}.")
            # set the seed for generating random numbers
            torch.manual_seed(int(random_seed))

        logger.info('...instantiating network for training run n. {}'.format(training_run))

        # create malware-NN model
        model = Net(use_malware=bool(use_malicious_labels),
                    use_counts=bool(use_count_labels),
                    use_tags=bool(use_tag_labels),
                    n_tags=len(Dataset.tags),  # get n_tags counting tags from the dataset
                    feature_dimension=feature_dimension)

        # use Adam optimizer on all the model parameters
        opt = torch.optim.Adam(model.parameters())

        # create generator (a.k.a. Dataloader)
        generator = get_generator(ds_root=ds_path,
                                  batch_size=batch_size,
                                  mode='train',
                                  num_workers=workers,
                                  n_samples=training_n_samples,
                                  use_malicious_labels=bool(use_malicious_labels),
                                  use_count_labels=bool(use_count_labels),
                                  use_tag_labels=bool(use_tag_labels))

        # create validation generator (a.k.a. validation Dataloader)
        val_generator = get_generator(ds_root=ds_path,
                                      batch_size=batch_size,
                                      mode='validation',
                                      num_workers=workers,
                                      n_samples=validation_n_samples,
                                      use_malicious_labels=bool(use_malicious_labels),
                                      use_count_labels=bool(use_count_labels),
                                      use_tag_labels=bool(use_tag_labels))

        # get number of steps per epoch (# of total batches) from generator
        steps_per_epoch = len(generator)
        # get number of validation steps per epoch (# of total validation batches) from validation generator
        val_steps_per_epoch = len(val_generator)

        # if run id was set -> resume training
        if run_id is not None:
            # get previously stopped run
            previous_run = mlflow.tracking.MlflowClient().get_run(run_id)

            # get artifact path previous run
            artifact_src_path = parse.unquote(
                parse.urlparse(os.path.join(previous_run.info.artifact_uri, "model_checkpoints")).path)
            # get artifact path from current run
            artifact_dest_path = parse.unquote(
                parse.urlparse(os.path.join(mlrun.info.artifact_uri, "model_checkpoints")).path)

            # copy logged artifacts of the resumed run in the current one
            shutil.copytree(artifact_src_path, artifact_dest_path)

            # define metrics to transfer
            metrics = ['valid_loss_total',
                       'valid_loss_jointEmbedding',
                       'train_loss_count',
                       'train_loss_malware',
                       'valid_loss_malware',
                       'train_loss_jointEmbedding',
                       'valid_loss_count',
                       'train_loss_total']

            # for each metric, get metric history from previous run and save them into the current run
            for metric in metrics:
                history = mlflow.tracking.MlflowClient().get_metric_history(run_id=run_id, key=metric)
                for m in history:
                    mlflow.log_metric(key=m.key, value=m.value, step=m.step)

        # get artifact path from current run
        artifact_path = parse.unquote(parse.urlparse(os.path.join(mlflow.get_artifact_uri(), "model_checkpoints")).path)

        # try loading the model from checkpoint (if it exists) and return epoch to start from
        start_epoch = model.load(artifact_path)

        # allocate model to selected device
        model.to(device)

        # loop for the selected number of epochs
        for epoch in range(start_epoch, epochs + 1):
            # instantiate a new dictionary-like object called loss_histories
            loss_histories = defaultdict(list)

            # set the model mode to 'train'
            model.train()

            # set start time
            start_time = time.time()

            # for all the training batches
            for i, (features, labels) in enumerate(generator):
                opt.zero_grad()  # clear old gradients from the last step

                # copy current features and allocate them on the selected device (CPU or GPU)
                features = deepcopy(features).to(device)

                # perform a forward pass through the network
                out = model(features)

                # compute loss given the predicted output from the model
                loss_dict = compute_loss(out, deepcopy(labels))  # copy the ground truth labels

                # extract total loss
                loss = loss_dict['total']

                # compute gradients
                loss.backward()

                # update model parameters
                opt.step()

                # for all the calculated losses in loss_dict
                for k in loss_dict.keys():
                    # if the loss is 'total' then append it to loss_histories['total'] after having detached it
                    # and passed it to the cpu
                    if k == 'total':
                        loss_histories[k].append(deepcopy(loss_dict[k].detach().cpu().item()))
                    # otherwise append the loss to loss_histories without having to detach it
                    else:
                        loss_histories[k].append(loss_dict[k])

                elapsed_time = time.time() - start_time

                # create loss string with the current losses
                loss_str = " ".join([f"{key} loss:{value:7.3f}" for key, value in loss_dict.items()])
                loss_str += " | "
                loss_str += " ".join([f"{key} mean:{np.mean(value):7.3f}" for key, value in loss_histories.items()])

                # write on standard out the loss string + other information
                sys.stdout.write('\r Epoch: {}/{} {}/{} '.format(epoch, epochs, i + 1, steps_per_epoch)
                                 + '[{}/{}, {:6.3f}it/s, RAM used: {:4.1f}%] '
                                 .format(time.strftime("%H:%M:%S", time.gmtime(elapsed_time)),
                                         time.strftime("%H:%M:%S",
                                                       time.gmtime(steps_per_epoch * elapsed_time / (i + 1))),
                                         (i + 1) / elapsed_time,
                                         psutil.virtual_memory().percent)
                                 + loss_str)

                # flush standard output
                sys.stdout.flush()
                del features, labels  # to avoid weird references that lead to generator errors

            # log mean losses
            for key, value in loss_histories.items():
                mlflow.log_metric("train_loss_" + key, np.mean(value), step=epoch)

            print()

            # instantiate a new dictionary-like object called loss_histories
            loss_histories = defaultdict(list)
            # set the model mode to 'eval'
            model.eval()

            # set start time
            start_time = time.time()

            # for all the validation batches
            for i, (features, labels) in enumerate(val_generator):
                # copy current features and allocate them on the selected device (CPU or GPU)
                features = deepcopy(features).to(device)

                with torch.no_grad():  # disable gradient calculation
                    # perform a forward pass through the network
                    out = model(features)

                # compute loss given the predicted output from the model
                loss_dict = compute_loss(out, deepcopy(labels))  # copy the ground truth labels

                # for all the calculated losses in loss_dict
                for k in loss_dict.keys():
                    # if the loss is 'total' then append it to loss_histories['total'] after having detached it
                    # and passed it to the cpu
                    if k == 'total':
                        loss_histories[k].append(deepcopy(loss_dict[k].detach().cpu().item()))
                    # otherwise append the loss to loss_histories without having to detach it
                    else:
                        loss_histories[k].append(loss_dict[k])

                elapsed_time = time.time() - start_time

                # create loss string with the current losses
                loss_str = " ".join([f"{key} loss:{value:7.3f}" for key, value in loss_dict.items()])
                loss_str += " | "
                loss_str += " ".join([f"{key} mean:{np.mean(value):7.3f}" for key, value in loss_histories.items()])

                # write on standard out the loss string + other information
                sys.stdout.write('\r Val: {}/{} {}/{} '.format(epoch, epochs, i + 1, val_steps_per_epoch)
                                 + '[{}/{}, {:6.3f}it/s, RAM used: {:4.1f}%] '
                                 .format(time.strftime("%H:%M:%S", time.gmtime(elapsed_time)),
                                         time.strftime("%H:%M:%S",
                                                       time.gmtime(steps_per_epoch * elapsed_time / (i + 1))),
                                         (i + 1) / elapsed_time,
                                         psutil.virtual_memory().percent)
                                 + loss_str)

                # flush standard output
                sys.stdout.flush()
                del features, labels  # to avoid weird references that lead to generator errors

            # log mean losses
            for key, value in loss_histories.items():
                mlflow.log_metric("valid_loss_" + key, np.mean(value), step=epoch)

            print()

            # save model in checkpoint dir
            model.save(epoch)

        logger.info('...done')


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()