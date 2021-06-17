import os  # provides a portable way of using operating system dependent functionality
import re  # provides regular expression matching operations
import tempfile  # used to create temporary files and directories
from copy import deepcopy  # creates a new object and recursively copies the original object elements

import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
import numpy as np  # the fundamental package for scientific computing with Python
import torch  # tensor library like NumPy, with strong GPU support
from torch import nn  # a neural networks library deeply integrated with autograd designed for maximum flexibility


class Net(nn.Module):
    """ Neural Network super class. """

    def __init__(self):
        """ Initialize net. """

        super().__init__()  # call __init__() method of nn.Module

    def forward(self,
                data) -> dict:  # current batch of data (features)
        """ Forward batch of data through the net.

        Args:
            data: Current batch of data (features)
        Returns:
            Dictionary containing predicted labels.
        """

        raise NotImplementedError

    def save(self,
             epoch):  # current epoch
        """ Saves model state dictionary to temp directory and then logs it.

        Args:
            epoch: Current epoch
        """

        # create temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # compute filename
            filename = os.path.join(temp_dir, "epoch_{}.pt".format(str(epoch)))

            # save model state of the current epoch to temp dir
            torch.save(self.state_dict(), filename)

            # log checkpoint file as artifact
            mlflow.log_artifact(filename, artifact_path="model_checkpoints")

    def load(self,
             path):  # path where to (try) retrieve model checkpoint from
        """ Loads model checkpoint from current run artifacts, if it exists.

        Args:
            path: Path where to (try) retrieve model checkpoint from
        Returns:
            Next epoch number.
        """

        # initialize last epoch done to 0
        last_epoch_done = 0
        # if the checkpoint directory exists
        if os.path.exists(path):
            # get the latest checkpoint epoch saved in checkpoint dir
            last_epoch_done = self.last_epoch_done(path)
            # if it is not none, load model state of the specified epoch from checkpoint dir
            if last_epoch_done is not None:
                self.load_state_dict(torch.load(os.path.join(path, "epoch_{}.pt".format(str(last_epoch_done)))))
            else:
                # otherwise just set last_epoch_done to 0
                last_epoch_done = 0

        # return next epoch to be done
        return last_epoch_done + 1

    @staticmethod
    def last_epoch_done(checkpoint_dir):  # path where to search the model state
        """ Get last epoch completed by a previous run.

        Args:
            checkpoint_dir: Path where to search the model state
        Returns:
            Epoch of the latest checkpoint if there are checkpoints in the directory provided, otherwise 'None'.
        """

        # set current highest epoch value
        max_epoch = None
        # get highest epoch from the model checkpoints present in the directory
        for epoch in [re.match(r'.*epoch_(\d+).pt', filename).group(1) for filename in os.listdir(checkpoint_dir)]:
            if max_epoch is None or epoch > max_epoch:
                max_epoch = epoch

        # return current highest epoch
        return max_epoch

    @staticmethod
    def compute_loss(predictions,  # a dictionary of results from a PENetwork model
                     labels,  # a dictionary of labels
                     loss_wts=None) -> dict:  # weights to assign to each head of the network (if it exists)
        """ Compute Net losses.

        Args:
            predictions: A dictionary of results from a Net model
            labels: A dictionary of labels
            loss_wts: Weights to assign to each head of the network (if it exists)
        Returns:
            Loss dictionary.
        """

        raise NotImplementedError

    @staticmethod
    def normalize_results(labels_dict,  # labels (ground truth) dictionary
                          results_dict,  # results (predicted labels) dictionary
                          use_malware=False,  # whether or not to use malware/benignware labels as a target
                          use_count=False,  # whether or not to use the counts as an additional target
                          use_tags=False) -> dict:  # whether or not to use SMART tags as additional targets
        """ Take a set of results dicts and break them out into a single dict of 1d arrays with appropriate column names
        that pandas can convert to a DataFrame.

        Args:
            labels_dict: Labels (ground truth) dictionary
            results_dict: Results (predicted labels) dictionary
            use_malware: Whether to use malware/benignware labels as a target
            use_count: Whether to use the counts as an additional target
            use_tags: Whether to use SMART tags as additional targets
        Returns:
            Dictionary containing labels and predictions.
        """

        raise NotImplementedError

    @staticmethod
    def detach_and_copy_array(array):  # numpy array or pytorch tensor to copy
        """ Detach numpy array or pytorch tensor and return a deep copy of it.

        Args:
            array: Numpy array or pytorch tensor to copy
        Returns:
            Deep copy of the array.
        """

        if isinstance(array, torch.Tensor):  # if the provided array is of type Tensor
            # return a copy of the array after having detached it, passed it to the cpu and finally flattened
            return deepcopy(array.cpu().detach().numpy()).ravel()
        elif isinstance(array, np.ndarray):  # else if it is of type ndarray
            # return a copy of the array after having flattened it
            return deepcopy(array).ravel()
        else:
            # otherwise raise an exception
            raise ValueError("Got array of unknown type {}".format(type(array)))
