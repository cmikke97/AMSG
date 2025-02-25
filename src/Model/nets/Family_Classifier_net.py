# Copyright 2021, Crepaldi Michele.
#
# Developed as a thesis project at the TORSEC research group of the Polytechnic of Turin (Italy) under the supervision
# of professor Antonio Lioy and engineer Andrea Atzeni and with the support of engineer Andrea Marcelli.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
# an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.

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
    """ Family Classifier Network built using the MTJE model as base. """

    def __init__(self,
                 families,  # list of families to predict
                 feature_dimension=2381,  # dimension of the input data feature vector
                 embedding_dimension=32,  # joint latent space size
                 layer_sizes=None,  # layer sizes (array of sizes)
                 fam_class_layer_sizes=None,  # layer sizes (array of sizes) for the family classifier
                 dropout_p=0.05,  # dropout probability
                 activation_function='elu',  # non-linear activation function to use
                 normalization_function='batch_norm'):  # normalization function to use
        """ Initialize net.

        Args:
            families: List of families to predict
            feature_dimension: Dimension of the input data feature vector (default: 2381)
            embedding_dimension: Joint latent space size (default: 32)
            layer_sizes: Layer sizes (array of sizes) (default: None -> use [512, 512, 128])
            fam_class_layer_sizes: Layer sizes (array of sizes) for the family classifier
                                   (default: None -> use [64, 32])
            dropout_p: Dropout probability (default: 0.05)
            activation_function: Non-linear activation function to use (may be "elu", "leakyRelu", "pRelu" or "relu")
                (default: "elu")
            normalization_function: Normalization function to use (may be "layer_norm" or "batch_norm")
                (default: "batch_norm")
        """

        self.families = families
        self.n_families = len(families)
        self.encoded_families = [idx for idx in range(self.n_families)]
        self.embedding_dimension = embedding_dimension

        # initialize super class
        super().__init__()

        layers = []  # initialize layers array
        fam_class_layers = []  # initialize fam_class_layers array

        # set loss criterion
        self.loss_criterion = nn.CrossEntropyLoss()

        # if layer_sizes was not defined (it is None) then initialize it to a default of [512, 512, 128]
        if layer_sizes is None:
            layer_sizes = [512, 512, 128]

        if fam_class_layer_sizes is None:
            fam_class_layer_sizes = [64, 32]

        # select activation function to use based on the activation_function parameter
        if activation_function.lower() == 'elu':
            self.activation_function = nn.ELU
        elif activation_function.lower() == 'leakyrelu':
            self.activation_function = nn.LeakyReLU
        elif activation_function.lower() == 'prelu':
            self.activation_function = nn.PReLU
        elif activation_function.lower() == 'relu':
            self.activation_function = nn.ReLU
        else:  # if the provided function is not recognised, raise error
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

        for i, ls in enumerate(fam_class_layer_sizes):
            if i == 0:
                fam_class_layers.append(nn.Linear(self.embedding_dimension, ls))
            else:
                fam_class_layers.append(nn.Linear(fam_class_layer_sizes[i - 1], ls))

            fam_class_layers.append(self.normalization_function(ls))  # append a Norm layer of size ls
            fam_class_layers.append(self.activation_function())  # append an ELU activation function module
            fam_class_layers.append(nn.Dropout(dropout_p))  # append a dropout layer with dropout probability dropout_p

        fam_class_layers.append(nn.Linear(fam_class_layer_sizes[-1], self.n_families))

        # create family classification head
        self.families_classifier = nn.Sequential(*tuple(fam_class_layers))
        self.softmax_output = nn.Softmax(dim=1)

    def forward(self,
                data):  # current batch of data (features)
        """ Forward batch of data through the net.

        Args:
            data: Current batch of data (features)
        Returns:
            Dictionary containing predicted family labels.
        """
        # get base result forwarding the data through the base model
        base_out = self.model_base(data)

        # get PE embedding
        pe_embedding = self.pe_embedding.forward(base_out)

        # calculate class scores
        scores = self.families_classifier(pe_embedding)

        return {'scores': scores, 'probs': self.softmax_output(scores)}

    def compute_loss(self,
                     predictions,  # a dictionary of results from the Net
                     labels,  # a dictionary of labels
                     loss_wts=None):  # weights to assign to each head of the network (if it exists)
        """ Compute Net loss.

        Args:
            predictions: A dictionary of results from the Net
            labels: A dictionary of labels
            loss_wts: Unused (default: None)
        Returns:
            Loss dictionary.
        """

        return self.loss_criterion(predictions['scores'], labels)  # calculate loss and return it

    def normalize_results(self,
                          labels,  # labels (ground truth)
                          predicted_probabilities,  # family probabilities predicted by the model
                          use_malware=False,  # whether or not to use malware/benignware labels as a target
                          use_count=False,  # whether or not to use the counts as an additional target
                          use_tags=False):  # whether or not to use SMART tags as additional targets
        """ Take a set of results dicts and break them out into a single dict of 1d arrays with appropriate column names
        that pandas can convert to a DataFrame.

        Args:
            labels: Labels (ground truth)
            predicted_probabilities: Family probabilities predicted by the model
            use_malware: Whether to use malware/benignware labels as a target (default: False)
            use_count: Whether to use the counts as an additional target (default: False)
            use_tags: Whether to use SMART tags as additional targets (default: False)
        Returns:
            Dictionary containing labels and predictions.
        """

        # a lot of deepcopies are done here to avoid a FD "leak" in the dataset generator
        # see here: https://github.com/pytorch/pytorch/issues/973#issuecomment-459398189

        rv = {'label': Net.detach_and_copy_array(labels)}  # initialize return value dict

        for column, family in enumerate(self.families):  # for all the families
            # normalize predicted probabilities array and save it into rv
            rv['proba_{}'.format(family)] = Net.detach_and_copy_array(predicted_probabilities[:, column])

        return rv
