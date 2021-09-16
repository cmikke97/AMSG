import configparser  # implements a basic configuration language for Python programs
import os  # provides a portable way of using operating system dependent functionality

from torch import nn  # a neural networks library deeply integrated with autograd designed for maximum flexibility

from .utils.Net import Net as baseNet

# get config file path
nets_dir = os.path.dirname(os.path.abspath(__file__))
model_dir = os.path.dirname(nets_dir)
src_dir = os.path.dirname(model_dir)
config_filepath = os.path.join(src_dir, 'config.ini')

# instantiate config parser and read config file
config = configparser.ConfigParser()
config.read(config_filepath)

# get variables from config file
device = config['general']['device']


class Net(baseNet):
    """ Joint Embedding Network which calculated embeddings similarity using the dot product. """

    def __init__(self,
                 feature_dimension=2381,  # dimension of the input data feature vector
                 embedding_dimension=32,  # joint latent space size
                 layer_sizes=None,  # layer sizes (array of sizes)
                 dropout_p=0.05,  # dropout probability
                 activation_function='elu',  # non-linear activation function to use
                 normalization_function='batch_norm'):  # normalization function to use
        """ Initialize net.

        Args:
            feature_dimension: Dimension of the input data feature vector
            embedding_dimension: Joint latent space size
            layer_sizes: Layer sizes (array of sizes)
            dropout_p: Dropout probability
            activation_function: Non-linear activation function to use (may be "elu", "leakyRelu", "pRelu" or "relu")
                (default: "elu")
            normalization_function: Normalization function to use (may be "layer_norm" or "batch_norm")
                (default: "batch_norm")
        """

        self.embedding_dimension = embedding_dimension

        # initialize super class
        super().__init__()

        layers = []  # initialize layers array

        # if layer_sizes was not defined (it is None) then initialize it to a default of [512, 512, 128]
        if layer_sizes is None:
            layer_sizes = [512, 512, 128]

        # select activation function to use based on the activation_function parameter
        if activation_function.lower() == 'elu':
            self.activation_function = nn.ELU
        elif activation_function.lower() == 'leakyrelu':
            self.activation_function = nn.LeakyReLU
        elif activation_function.lower() == 'prelu':
            self.activation_function = nn.PReLU
        elif activation_function.lower() == 'relu':
            self.activation_function = nn.ReLU
        else:  # if the provided activation function is not recognised, raise error
            raise ValueError('Unknown activation function {}. Try "elu", "leakyRelu", "pRelu" or "relu"'
                             .format(activation_function))

        # select normalization function to use based on the normalization_function parameter
        if normalization_function.lower() == 'layer_norm':
            self.normalization_function = nn.LayerNorm
        elif normalization_function.lower() == 'batch_norm':
            self.normalization_function = nn.BatchNorm1d
        else:  # if the provided normalization function is not recognised, raise error
            raise ValueError('Unknown activation function {}. Try "layer_norm" or "batch_norm"'
                             .format(activation_function))

        # for each layer size in layer_sizes
        for i, ls in enumerate(layer_sizes):
            if i == 0:
                # append the first Linear Layer with dimensions feature_dimension x ls
                layers.append(nn.Linear(feature_dimension, ls))
            else:
                # append a Linear Layer with dimensions layer_sizes[i-1] x ls
                layers.append(nn.Linear(layer_sizes[i - 1], ls))

            layers.append(self.normalization_function(ls))  # append a Norm layer of size ls
            layers.append(self.activation_function())  # append an ELU activation function module
            layers.append(nn.Dropout(dropout_p))  # append a dropout layer with probability of dropout dropout_p

        # create a tuple from the layers list, then apply nn.Sequential to get a sequential container
        # -> this will be the model base
        self.model_base = nn.Sequential(*tuple(layers))

        # create pe embedding head
        self.pe_embedding = nn.Sequential(nn.Linear(layer_sizes[-1], self.embedding_dimension),
                                          self.normalization_function(self.embedding_dimension),
                                          self.activation_function())

    def forward(self,
                data):  # current batch of data (features)
        """ Forward batch of data through the net.

        Args:
            data: Current batch of data (features)
        Returns:
            Dictionary containing predicted labels.
        """

        # get base result forwarding the data through the base model
        base_out = self.model_base(data)

        # get PE embedding
        pe_embedding = self.pe_embedding(base_out)

        return pe_embedding  # return embedding

    @staticmethod
    def compute_loss(predictions,  # a dictionary of results from the Net
                     labels,  # a dictionary of labels
                     loss_wts=None):  # weights to assign to each head of the network (if it exists)
        """ Compute Net losses (optionally with SMART tags and vendor detection count auxiliary losses).

        Args:
            predictions: A dictionary of results from the Net
            labels: A dictionary of labels
            loss_wts: Weights to assign to each head of the network (if it exists); defaults to values used in the
                      ALOHA paper (1.0 for malware, 0.1 for count and each tag)
        Returns:
            Loss dictionary.
        """

        pass

    @staticmethod
    def normalize_results(labels_dict,  # labels (ground truth) dictionary
                          results_dict,  # results (predicted labels) dictionary
                          use_malware=False,  # whether or not to use malware/benignware labels as a target
                          use_count=False,  # whether or not to use the counts as an additional target
                          use_tags=False):  # whether or not to use SMART tags as additional targets
        """ Take a set of results dicts and break them out into a single dict of 1d arrays with appropriate column names
        that pandas can convert to a DataFrame.

        Args:
            labels_dict: Labels (ground truth) dictionary
            results_dict: Results (predicted labels) dictionary
            use_malware: Whether to use malware/benignware labels as a target
            use_count: Whether to use the counts as an additional target
            use_tags: Whether to use SMART tags as additional targets. NOTE: this is here just for compatibility with
                      the evaluation procedure. With the joint embedding network the tags will always be used, even if
                      this flag is false.
        Returns:
            Dictionary containing labels and predictions.
        """

        pass
