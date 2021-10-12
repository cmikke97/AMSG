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
import json  # json encoder and decoder
import os  # provides a portable way of using operating system dependent functionality
from urllib import parse  # standard interface to break Uniform Resource Locator (URL) in components

import baker  # easy, powerful access to Python functions from the command line
import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
from logzero import logger  # robust and effective logging for Python
from mlflow.utils import mlflow_tags  # mlflow tags

from FreshDatasetBuilder.utils.fresh_dataset_utils import check_files as fresh_check_files
from Sorel20mDataset.utils.download_utils import check_files as download_check_files
from Sorel20mDataset.utils.preproc_utils import check_files as preproc_check_files
from utils.workflow_utils import Hash, get_or_run, run

# get config file path
src_dir = os.path.dirname(os.path.abspath(__file__))
config_filepath = os.path.join(src_dir, 'config.ini')

# instantiate config parser and read config file
config = configparser.ConfigParser()
config.read(config_filepath)


@baker.command
def workflow(base_dir,  # base tool path
             use_cache=1,  # whether to skip already executed runs (in cache) or not (1/0)
             ignore_git=0):  # whether to ignore git version or not (1/0)
    """ Automatic Malware Signature Generation MLflow workflow.

    Args:
        base_dir: Base tool path
        use_cache: Whether to skip already executed runs (in cache) or not (1/0)
        ignore_git: Whether to ignore git version or not (1/0)
    """

    # get some needed variables from config file
    runs = int(config['general']['runs'])
    workers = int(config['general']['workers'])

    batch_size = int(config['mtje']['batch_size'])
    epochs = int(config['mtje']['epochs'])
    use_malicious_labels = int(config['mtje']['use_malicious_labels'])
    use_count_labels = int(config['mtje']['use_count_labels'])
    gen_type = config['mtje']['gen_type']
    similarity_measure = config['mtje']['similarity_measure'].lower()
    net_type = 'mtje'

    training_n_samples = int(config['sorel20mDataset']['training_n_samples'])
    validation_n_samples = int(config['sorel20mDataset']['validation_n_samples'])
    test_n_samples = int(config['sorel20mDataset']['test_n_samples'])

    min_n_anchor_samples = int(config['freshDataset']['min_n_anchor_samples'])
    max_n_anchor_samples = int(config['freshDataset']['max_n_anchor_samples'])
    fresh_n_queries = int(config['freshDataset']['n_queries'])
    n_evaluations = int(config['freshDataset']['n_evaluations'])

    f_c_epochs = int(config['familyClassifier']['epochs'])
    f_c_train_split_proportion = int(config['familyClassifier']['train_split_proportion'])
    f_c_valid_split_proportion = int(config['familyClassifier']['valid_split_proportion'])
    f_c_test_split_proportion = int(config['familyClassifier']['test_split_proportion'])
    f_c_batch_size = int(config['familyClassifier']['batch_size'])

    c_l_epochs = int(config['contrastiveLearning']['epochs'])
    c_l_train_split_proportion = int(config['contrastiveLearning']['train_split_proportion'])
    c_l_valid_split_proportion = int(config['contrastiveLearning']['valid_split_proportion'])
    c_l_test_split_proportion = int(config['contrastiveLearning']['test_split_proportion'])
    c_l_batch_size = int(config['contrastiveLearning']['batch_size'])
    c_l_rank_size = int(config['contrastiveLearning']['rank_size'])
    c_l_knn_k_min = int(config['contrastiveLearning']['knn_k_min'])
    c_l_knn_k_max = int(config['contrastiveLearning']['knn_k_max'])

    # initialize Hash object
    ch = Hash()

    # update hash with the content of the config file (for the current net type)
    ch.update(json.dumps(dict(config.items('sorel20mDataset'))))
    # get config file sha256 digest
    dataset_config_sha = ch.get_b64()

    # update hash with the content of the config file (for the current net type)
    ch.update(json.dumps(dict(config.items(net_type))))
    # get config file sha256 digest
    config_sha = ch.get_b64()

    # update hash with the content of the config file (for the freshDataset)
    ch.update(json.dumps(dict(config.items('freshDataset'))))
    # get config file sha256 digest
    fresh_dataset_config_sha = ch.get_b64()

    # create copy of the current config hash digest
    ch_copy = ch.copy()

    # update hash with the content of the config file (for the freshDataset)
    ch.update(json.dumps(dict(config.items('familyClassifier'))))
    # get config file sha256 digest
    family_class_config_sha = ch.get_b64()

    # update hash with the content of the config file (for the freshDataset)
    ch_copy.update(json.dumps(dict(config.items('contrastiveLearning'))))
    # get config file sha256 digest
    contr_learn_config_sha = ch_copy.get_b64()

    # instantiate key-n_samples dict
    n_samples_dict = {'train': training_n_samples,
                      'validation': validation_n_samples,
                      'test': test_n_samples}

    # Note: The entrypoint names are defined in MLproject. The artifact directories
    # are documented by each step's .py file.

    # start mlflow run
    with mlflow.start_run() as active_run:
        # get code git commit version
        git_commit = active_run.data.tags.get(mlflow_tags.MLFLOW_GIT_COMMIT)

        # log config file
        mlflow.log_text(json.dumps({s: dict(config.items(s)) for s in config.sections()}), 'config.txt')

        # set dataset destination dir
        dataset_dir = os.path.join(base_dir, 'dataset')
        # set dataset base path (directory containing 'meta.db')
        dataset_base_path = os.path.join(dataset_dir, '09-DEC-2020', 'processed-data')
        # set pre-processed dataset base path (directory containing .dat files)
        pre_processed_dataset_dir = os.path.join(dataset_dir, '09-DEC-2020', 'pre-processed_dataset')
        # set fresh dataset base path (directory containing .dat files)
        fresh_dataset_dir = os.path.join(dataset_dir, 'fresh_dataset')

        # if pre-processed dataset files for this run parameters are not present, generate them
        if not preproc_check_files(destination_dir=pre_processed_dataset_dir,
                                   n_samples_dict=n_samples_dict):
            logger.info("Pre-processed dataset not found.")

            # if the original Sorel20M dataset is not present, download it
            if not download_check_files(dataset_dir):
                logger.info("Dataset not found.")

                # run dataset downloader
                download_dataset_run = run("download_dataset", {
                    'destination_dir': dataset_dir
                }, config_sha=dataset_config_sha)

            # pre-process dataset
            preprocess_dataset_run = run("preprocess_dataset", {
                'ds_path': dataset_base_path,
                'destination_dir': pre_processed_dataset_dir,
                'training_n_samples': training_n_samples,
                'validation_n_samples': validation_n_samples,
                'test_n_samples': test_n_samples,
                'batch_size': batch_size,
                'remove_missing_features': str(os.path.join(dataset_base_path, "shas_missing_ember_features.json"))
            }, config_sha=dataset_config_sha)

        # if the fresh dataset is not present, generate it
        if not fresh_check_files(fresh_dataset_dir):
            logger.info("Fresh dataset not found.")

            # generate fresh dataset
            build_fresh_dataset_run = run("build_fresh_dataset", {
                'dataset_dest_dir': fresh_dataset_dir
            }, config_sha=fresh_dataset_config_sha)

        # initialize results files dicts
        results_files = {}
        c_l_results_files = {}

        # instantiate common (between consecutive training runs) training parameters
        common_training_params = {
            'ds_path': pre_processed_dataset_dir,
            'net_type': net_type if similarity_measure == 'dot' else net_type + '_{}'.format(similarity_measure),
            'gen_type': gen_type,
            'batch_size': batch_size,
            'epochs': epochs,
            'training_n_samples': training_n_samples,
            'validation_n_samples': validation_n_samples,
            'use_malicious_labels': use_malicious_labels,
            'use_count_labels': use_count_labels,
            'workers': workers
        }

        # instantiate common (between consecutive training runs) evaluation parameters
        common_evaluation_params = {
            'ds_path': pre_processed_dataset_dir,
            'net_type': net_type if similarity_measure == 'dot' else net_type + '_{}'.format(similarity_measure),
            'gen_type': gen_type,
            'batch_size': batch_size,
            'test_n_samples': test_n_samples,
            'evaluate_malware': use_malicious_labels,
            'evaluate_count': use_count_labels
        }

        # for each training run
        for training_run_id in range(runs):
            logger.info("initiating training run n. {}".format(str(training_run_id)))

            # -- Model Training and Evaluation Steps -------------------------------------------------------------------
            # set training parameters
            training_params = common_training_params
            training_params.update({'training_run': training_run_id})

            # train network (get or run) on Sorel20M dataset
            training_run = get_or_run("train_network",
                                      training_params,
                                      git_commit,
                                      ignore_git=bool(ignore_git),
                                      use_cache=bool(use_cache),
                                      resume=True,
                                      config_sha=config_sha)

            # get model checkpoints path
            checkpoint_path = parse.unquote(parse.urlparse(os.path.join(training_run.info.artifact_uri,
                                                                        "model_checkpoints")).path)

            # set model checkpoint filename
            checkpoint_file = os.path.join(checkpoint_path, "epoch_{}.pt".format(epochs))

            # set evaluation parameters
            evaluation_params = common_evaluation_params
            evaluation_params.update({'checkpoint_file': checkpoint_file})

            # evaluate model against Sorel20M dataset
            evaluation_run = get_or_run("evaluate_network",
                                        evaluation_params,
                                        git_commit,
                                        ignore_git=bool(ignore_git),
                                        use_cache=bool(use_cache),
                                        config_sha=config_sha)

            # get model evaluation results path
            results_path = parse.unquote(parse.urlparse(os.path.join(evaluation_run.info.artifact_uri,
                                                                     "model_results")).path)

            # set model evaluation results filename
            results_file = os.path.join(results_path, "results.csv")

            # add file path to results_files dictionary (used for plotting mean results)
            results_files["run_id_" + str(training_run_id)] = results_file

            # compute (and plot) all tagging results
            all_tagging_results_run = get_or_run("compute_all_run_results", {
                'results_file': results_file,
                'use_malicious_labels': use_malicious_labels,
                'use_tag_labels': 1
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=config_sha)
            # ----------------------------------------------------------------------------------------------------------

            # -- Model Evaluation using Fresh Dataset Steps ------------------------------------------------------------
            # evaluate model against fresh dataset
            fresh_evaluation_run = get_or_run("evaluate_fresh", {
                'fresh_ds_path': fresh_dataset_dir,
                'checkpoint_path': checkpoint_file,
                'net_type': net_type if similarity_measure == 'dot' else net_type + '_{}'.format(similarity_measure),
                'min_n_anchor_samples': min_n_anchor_samples,
                'max_n_anchor_samples': max_n_anchor_samples,
                'n_query_samples': fresh_n_queries,
                'n_evaluations': n_evaluations
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=fresh_dataset_config_sha)

            # get model evaluation results path
            fresh_results_path = parse.unquote(parse.urlparse(os.path.join(fresh_evaluation_run.info.artifact_uri,
                                                                           "fresh_prediction_results")).path)

            # set model evaluation results filename
            fresh_results_file = os.path.join(fresh_results_path, "fresh_prediction_results.json")

            # compute (and plot) all family prediction results (on fresh dataset)
            all_tagging_results_run = get_or_run("compute_all_run_fresh_results", {
                'results_file': fresh_results_file
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=fresh_dataset_config_sha)
            # ----------------------------------------------------------------------------------------------------------

            # -- Family Classifier Steps -------------------------------------------------------------------------------
            # create family classifier from previously trained network and train it on fresh dataset
            f_c_train_run = get_or_run("train_family_classifier", {
                'fresh_ds_path': fresh_dataset_dir,
                'checkpoint_path': checkpoint_file,
                'epochs': f_c_epochs,
                'training_run': training_run_id,
                'train_split_proportion': f_c_train_split_proportion,
                'valid_split_proportion': f_c_valid_split_proportion,
                'test_split_proportion': f_c_test_split_proportion,
                'batch_size': f_c_batch_size
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=family_class_config_sha)

            # get model checkpoints path
            f_c_checkpoint_path = parse.unquote(parse.urlparse(os.path.join(f_c_train_run.info.artifact_uri,
                                                                            "model_checkpoints")).path)

            # set model checkpoint filename
            f_c_checkpoint_file = os.path.join(f_c_checkpoint_path, "epoch_{}.pt".format(f_c_epochs))

            # evaluate model against fresh dataset
            f_c_eval_run = get_or_run("evaluate_family_classifier", {
                'fresh_ds_path': fresh_dataset_dir,
                'checkpoint_path': f_c_checkpoint_file,
                'training_run': training_run_id,
                'train_split_proportion': f_c_train_split_proportion,
                'valid_split_proportion': f_c_valid_split_proportion,
                'test_split_proportion': f_c_test_split_proportion,
                'batch_size': f_c_batch_size
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=family_class_config_sha)

            # get model evaluation results path
            f_c_results_path = parse.unquote(parse.urlparse(os.path.join(f_c_eval_run.info.artifact_uri,
                                                                         "family_class_results")).path)

            # set model evaluation results filename
            f_c_results_file = os.path.join(f_c_results_path, "results.csv")

            # compute (and plot) all tagging results
            f_c_compute_results_run = get_or_run("compute_all_family_class_results", {
                'results_file': f_c_results_file,
                'fresh_ds_path': fresh_dataset_dir
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=family_class_config_sha)
            # ----------------------------------------------------------------------------------------------------------

            # -- Contrastive Learning Steps ----------------------------------------------------------------------------
            # create family classifier from previously trained network and train it on fresh dataset
            c_l_train_run = get_or_run("train_contrastive_model", {
                'fresh_ds_path': fresh_dataset_dir,
                'checkpoint_path': checkpoint_file,
                'epochs': c_l_epochs,
                'training_run': training_run_id,
                'train_split_proportion': c_l_train_split_proportion,
                'valid_split_proportion': c_l_valid_split_proportion,
                'test_split_proportion': c_l_test_split_proportion,
                'batch_size': c_l_batch_size
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=contr_learn_config_sha)

            # get model checkpoints path
            c_l_checkpoint_path = parse.unquote(parse.urlparse(os.path.join(c_l_train_run.info.artifact_uri,
                                                                            "model_checkpoints")).path)

            # set model checkpoint filename
            c_l_checkpoint_file = os.path.join(c_l_checkpoint_path, "epoch_{}.pt".format(c_l_epochs))

            # evaluate model against fresh dataset
            c_l_eval_run = get_or_run("evaluate_contrastive_model", {
                'fresh_ds_path': fresh_dataset_dir,
                'checkpoint_path': c_l_checkpoint_file,
                'training_run': training_run_id,
                'train_split_proportion': c_l_train_split_proportion,
                'valid_split_proportion': c_l_valid_split_proportion,
                'test_split_proportion': c_l_test_split_proportion,
                'batch_size': c_l_batch_size,
                'rank_size': c_l_rank_size,
                'knn_k_min': c_l_knn_k_min,
                'knn_k_max': c_l_knn_k_max
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=contr_learn_config_sha)

            # get model evaluation results path
            c_l_results_path = parse.unquote(parse.urlparse(os.path.join(c_l_eval_run.info.artifact_uri,
                                                                         "contrastive_learning_results")).path)

            # set model evaluation results filename
            c_l_results_file = os.path.join(c_l_results_path, "results.csv")

            # compute (and plot) all tagging results
            c_l_compute_results_run = get_or_run("compute_contrastive_learning_results", {
                'results_file': c_l_results_file,
                'fresh_ds_path': fresh_dataset_dir,
                'knn_k_min': c_l_knn_k_min,
                'knn_k_max': c_l_knn_k_max
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=contr_learn_config_sha)

            # get model evaluation results path
            c_l_scores_dir_path = parse.unquote(parse.urlparse(os.path.join(c_l_compute_results_run.info.artifact_uri,
                                                                            "contrastive_learning_scores")).path)

            # add dir path to c_l_results_files dictionary (used for plotting mean score trends)
            c_l_results_files["run_id_" + str(training_run_id)] = c_l_scores_dir_path
            # ----------------------------------------------------------------------------------------------------------

        # create temp dir name using the value from config_sha (sha of some parts of the config file).
        # -> This is done in order to have a different (but predictable) run_to_filename at each set of runs with
        # different parameters. This allows mlflow to know when it is needed to run 'per_tag_plot_runs'. If, on the
        # other hand a simple tempfile.TemporaryDirectory() was used then mlflow would run 'per_tag_plot_runs' every
        # time, even if a precedent run was available (because the parameter 'run_to_filename_json' would be different)
        tempdir = os.path.join(base_dir, 'tmp_{}'.format(config_sha))
        # create temp dir
        os.makedirs(tempdir, exist_ok=True)

        # create contrastive learning temp dir name using the value from config_sha (sha of some parts of the config
        # file). -> This is done in order to have a different (but predictable) run_to_filename at each set of runs with
        # different parameters. This allows mlflow to know when it is needed to run 'per_tag_plot_runs'. If, on the
        # other hand a simple tempfile.TemporaryDirectory() was used then mlflow would run 'per_tag_plot_runs' every
        # time, even if a precedent run was available (because the parameter 'run_to_filename_json' would be different)
        c_l_tempdir = os.path.join(base_dir, 'tmp_{}'.format(contr_learn_config_sha))
        # create temp dir
        os.makedirs(c_l_tempdir, exist_ok=True)

        # set run-to-filename file path
        run_to_filename = os.path.join(tempdir, "results.json")

        # create and open the results.json file in write mode
        with open(run_to_filename, "w") as output_file:
            # save results_files dictionary as a json file
            json.dump(results_files, output_file)

        mlflow.log_artifact(run_to_filename, "run_to_filename")

        # set run-to-filename file path
        c_l_run_to_filename = os.path.join(c_l_tempdir, "c_l_results.json")

        # create and open the c_l_results.json file in write mode
        with open(c_l_run_to_filename, "w") as output_file:
            # save c_l_results_files dictionary as a json file
            json.dump(c_l_results_files, output_file)

        mlflow.log_artifact(c_l_run_to_filename, "run_to_filename")

        # if there is more than 1 run, compute also per-tag mean results
        if runs > 1:
            # plot all roc distributions
            per_tag_plot_runs = get_or_run("plot_all_roc_distributions", {
                'run_to_filename_json': run_to_filename,
                'use_malicious_labels': use_malicious_labels,
                'use_tag_labels': 1
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=config_sha)

            # plot all model mean scores trends
            plot_all_scores_trends = get_or_run("plot_all_contrastive_scores_trends", {
                'run_to_filename_json': c_l_run_to_filename,
                'knn_k_min': c_l_knn_k_min,
                'knn_k_max': c_l_knn_k_max
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=contr_learn_config_sha)

        # remove temp files and temporary directory
        os.remove(run_to_filename)
        # os.remove(fresh_run_to_filename)
        os.rmdir(tempdir)

        # remove contrastive learning temp files and temporary directory
        os.remove(c_l_run_to_filename)
        # os.remove(fresh_run_to_filename)
        os.rmdir(c_l_tempdir)


@baker.command
def aloha_workflow(base_dir,  # base tool path
                   use_cache=1,  # whether to skip already executed runs (in cache) or not (1/0)
                   ignore_git=0):  # whether to ignore git version or not (1/0)
    """ Base detection MLflow workflow.

    Args:
        base_dir: Base tool path
        use_cache: Whether to skip already executed runs (in cache) or not (1/0)
        ignore_git: Whether to ignore git version or not (1/0)
    """

    # get some needed variables from config file
    runs = int(config['general']['runs'])
    workers = int(config['general']['workers'])

    batch_size = int(config['aloha']['batch_size'])
    epochs = int(config['aloha']['epochs'])
    use_malicious_labels = int(config['aloha']['use_malicious_labels'])
    use_count_labels = int(config['aloha']['use_count_labels'])
    use_tag_labels = int(config['aloha']['use_tag_labels'])
    gen_type = config['aloha']['gen_type']
    net_type = 'aloha'

    training_n_samples = int(config['sorel20mDataset']['training_n_samples'])
    validation_n_samples = int(config['sorel20mDataset']['validation_n_samples'])
    test_n_samples = int(config['sorel20mDataset']['test_n_samples'])

    min_n_anchor_samples = int(config['freshDataset']['min_n_anchor_samples'])
    max_n_anchor_samples = int(config['freshDataset']['max_n_anchor_samples'])
    fresh_n_queries = int(config['freshDataset']['n_queries'])
    n_evaluations = int(config['freshDataset']['n_evaluations'])

    # initialize Hash object
    ch = Hash()

    # update hash with the content of the config file (for the current net type)
    ch.update(json.dumps(dict(config.items('sorel20mDataset'))))
    # get config file sha256 digest
    dataset_config_sha = ch.get_b64()

    # update hash with the content of the config file (for the current net type)
    ch.update(json.dumps(dict(config.items(net_type))))
    # get config file sha256 digest
    config_sha = ch.get_b64()

    # update hash with the content of the config file (for the freshDataset)
    ch.update(json.dumps(dict(config.items('freshDataset'))))
    # get config file sha256 digest
    fresh_dataset_config_sha = ch.get_b64()

    # instantiate key-n_samples dict
    n_samples_dict = {'train': training_n_samples,
                      'validation': validation_n_samples,
                      'test': test_n_samples}

    # Note: The entrypoint names are defined in MLproject. The artifact directories
    # are documented by each step's .py file.

    # start mlflow run
    with mlflow.start_run() as active_run:
        # get code git commit version
        git_commit = active_run.data.tags.get(mlflow_tags.MLFLOW_GIT_COMMIT)

        # log config file
        mlflow.log_text(json.dumps({s: dict(config.items(s)) for s in config.sections()}), 'config.txt')

        # set dataset destination dir
        dataset_dir = os.path.join(base_dir, 'dataset')
        # set dataset base path (directory containing 'meta.db')
        dataset_base_path = os.path.join(dataset_dir, '09-DEC-2020', 'processed-data')
        # set pre-processed dataset base path (directory containing .dat files)
        pre_processed_dataset_dir = os.path.join(dataset_dir, '09-DEC-2020', 'pre-processed_dataset')
        # set fresh dataset base path (directory containing .dat files)
        fresh_dataset_dir = os.path.join(dataset_dir, 'fresh_dataset')

        # if pre-processed dataset files for this run parameters are not present, generate them
        if not preproc_check_files(destination_dir=pre_processed_dataset_dir,
                                   n_samples_dict=n_samples_dict):
            logger.info("Pre-processed dataset not found.")

            # if the original Sorel20M dataset is not present, download it
            if not download_check_files(dataset_dir):
                logger.info("Dataset not found.")

                # run dataset downloader
                download_dataset_run = run("download_dataset", {
                    'destination_dir': dataset_dir
                }, config_sha=dataset_config_sha)

            # pre-process dataset
            preprocess_dataset_run = run("preprocess_dataset", {
                'ds_path': dataset_base_path,
                'destination_dir': pre_processed_dataset_dir,
                'training_n_samples': training_n_samples,
                'validation_n_samples': validation_n_samples,
                'test_n_samples': test_n_samples,
                'batch_size': batch_size,
                'remove_missing_features': str(os.path.join(dataset_base_path, "shas_missing_ember_features.json"))
            }, config_sha=dataset_config_sha)

        # if the fresh dataset is not present, generate it
        if not fresh_check_files(fresh_dataset_dir):
            logger.info("Fresh dataset not found.")

            # generate fresh dataset
            build_fresh_dataset_run = run("build_fresh_dataset", {
                'dataset_dest_dir': fresh_dataset_dir
            }, config_sha=fresh_dataset_config_sha)

        results_files = {}

        # instantiate common (between consecutive training runs) training parameters
        common_training_params = {
            'ds_path': pre_processed_dataset_dir,
            'net_type': net_type,
            'gen_type': gen_type,
            'batch_size': batch_size,
            'epochs': epochs,
            'training_n_samples': training_n_samples,
            'validation_n_samples': validation_n_samples,
            'use_malicious_labels': use_malicious_labels,
            'use_count_labels': use_count_labels,
            'use_tag_labels': use_tag_labels,
            'workers': workers
        }

        # instantiate common (between consecutive training runs) evaluation parameters
        common_evaluation_params = {
            'ds_path': pre_processed_dataset_dir,
            'net_type': net_type,
            'gen_type': gen_type,
            'batch_size': batch_size,
            'test_n_samples': test_n_samples,
            'evaluate_malware': use_malicious_labels,
            'evaluate_count': use_count_labels
        }

        # for each training run
        for training_run_id in range(runs):
            logger.info("initiating training run n. {}".format(str(training_run_id)))

            # set training parameters
            training_params = common_training_params
            training_params.update({'training_run': training_run_id})

            # train network (get or run) on Sorel20M dataset
            training_run = get_or_run("train_network",
                                      training_params,
                                      git_commit,
                                      ignore_git=bool(ignore_git),
                                      use_cache=bool(use_cache),
                                      resume=True,
                                      config_sha=config_sha)

            # get model checkpoints path
            checkpoint_path = parse.unquote(parse.urlparse(os.path.join(training_run.info.artifact_uri,
                                                                        "model_checkpoints")).path)

            # set model checkpoint filename
            checkpoint_file = os.path.join(checkpoint_path, "epoch_{}.pt".format(epochs))

            # set evaluation parameters
            evaluation_params = common_evaluation_params
            evaluation_params.update({'checkpoint_file': checkpoint_file})

            # evaluate model against Sorel20M dataset
            evaluation_run = get_or_run("evaluate_network",
                                        evaluation_params,
                                        git_commit,
                                        ignore_git=bool(ignore_git),
                                        use_cache=bool(use_cache),
                                        config_sha=config_sha)

            # get model evaluation results path
            results_path = parse.unquote(parse.urlparse(os.path.join(evaluation_run.info.artifact_uri,
                                                                     "model_results")).path)

            # set model evaluation results filename
            results_file = os.path.join(results_path, "results.csv")

            # add file path to results_files dictionary (used for plotting mean results)
            results_files["run_id_" + str(training_run_id)] = results_file

            # compute (and plot) all tagging results
            all_tagging_results_run = get_or_run("compute_all_run_results", {
                'results_file': results_file,
                'use_malicious_labels': use_malicious_labels,
                'use_tag_labels': use_tag_labels
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=config_sha)

            # evaluate model against fresh dataset
            fresh_evaluation_run = get_or_run("evaluate_fresh", {
                'fresh_ds_path': fresh_dataset_dir,
                'checkpoint_path': checkpoint_file,
                'net_type': net_type,
                'min_n_anchor_samples': min_n_anchor_samples,
                'max_n_anchor_samples': max_n_anchor_samples,
                'n_query_samples': fresh_n_queries,
                'n_evaluations': n_evaluations
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=fresh_dataset_config_sha)

            # get model evaluation results path
            fresh_results_path = parse.unquote(parse.urlparse(os.path.join(fresh_evaluation_run.info.artifact_uri,
                                                                           "fresh_prediction_results")).path)

            # set model evaluation results filename
            fresh_results_file = os.path.join(fresh_results_path, "fresh_prediction_results.json")

            # compute (and plot) all family prediction results (on fresh dataset)
            all_tagging_results_run = get_or_run("compute_all_run_fresh_results", {
                'results_file': fresh_results_file
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=fresh_dataset_config_sha)

        # get overall parameters set (without duplicates and sorted)
        params_set = [str(p) for p in common_training_params.values()]
        params_set.extend([str(p) for p in common_evaluation_params.values() if str(p) not in params_set])
        params_set.sort()

        # instantiate hash
        h = Hash()
        # for each param in the parameters set, update the hash value
        for param in params_set:
            h.update(str(param))

        # create temp dir name using the value from the hash object.
        # -> This is done in order to have a different (but predictable) run_to_filename at each different run.
        # This in turn means that mlflow knows when it is needed to run 'per_tag_plot_runs'.
        tempdir = os.path.join(base_dir, 'tmp_{}'.format(h.get_b64()))
        os.makedirs(tempdir, exist_ok=True)

        # set run-to-filename file path
        run_to_filename = os.path.join(tempdir, "results.json")

        # create and open the results.json file in write mode
        with open(run_to_filename, "w") as output_file:
            # save results_files dictionary as a json file
            json.dump(results_files, output_file)

        # log run-to-filename
        mlflow.log_artifact(run_to_filename, "run_to_filename")

        # if there is more than 1 run, compute also per-tag mean results
        if runs > 1:
            # plot all roc distributions
            per_tag_plot_runs = get_or_run("plot_all_roc_distributions", {
                'run_to_filename_json': run_to_filename,
                'use_malicious_labels': use_malicious_labels,
                'use_tag_labels': use_tag_labels
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=config_sha)

        # remove temporary directory and run_to_filename file
        os.remove(run_to_filename)
        os.rmdir(tempdir)


@baker.command
def family_classifier_only(base_dir,  # base tool path
                           use_cache=1,  # whether to skip already executed runs (in cache) or not (1/0)
                           ignore_git=0):  # whether to ignore git version or not (1/0)
    """ Automatic Malware Signature Generation MLflow workflow.

    Args:
        base_dir: Base tool path
        use_cache: Whether to skip already executed runs (in cache) or not (1/0)
        ignore_git: Whether to ignore git version or not (1/0)
    """

    # get some needed variables from config file
    runs = int(config['general']['runs'])
    net_type = 'mtje'

    training_n_samples = int(config['sorel20mDataset']['training_n_samples'])
    validation_n_samples = int(config['sorel20mDataset']['validation_n_samples'])
    test_n_samples = int(config['sorel20mDataset']['test_n_samples'])

    f_c_epochs = int(config['familyClassifier']['epochs'])
    f_c_train_split_proportion = int(config['familyClassifier']['train_split_proportion'])
    f_c_valid_split_proportion = int(config['familyClassifier']['valid_split_proportion'])
    f_c_test_split_proportion = int(config['familyClassifier']['test_split_proportion'])
    f_c_batch_size = int(config['familyClassifier']['batch_size'])

    # initialize Hash object
    ch = Hash()
    # update hash with the content of the config file (for the current net type)
    ch.update(json.dumps(dict(config.items(net_type))))
    # update hash with the content of the config file (for the freshDataset)
    ch.update(json.dumps(dict(config.items('freshDataset'))))
    # get config file sha256 digest
    fresh_eval_config_sha = ch.get_b64()

    # update hash with the content of the config file (for the freshDataset)
    ch.update(json.dumps(dict(config.items('familyClassifier'))))
    # get config file sha256 digest
    family_class_config_sha = ch.get_b64()

    # instantiate key-n_samples dict
    n_samples_dict = {'train': training_n_samples,
                      'validation': validation_n_samples,
                      'test': test_n_samples}

    # Note: The entrypoint names are defined in MLproject. The artifact directories
    # are documented by each step's .py file.

    # start mlflow run
    with mlflow.start_run() as active_run:
        # get code git commit version
        git_commit = active_run.data.tags.get(mlflow_tags.MLFLOW_GIT_COMMIT)

        # log config file
        mlflow.log_text(json.dumps({s: dict(config.items(s)) for s in config.sections()}), 'config.txt')

        # set dataset destination dir
        dataset_dir = os.path.join(base_dir, 'dataset')
        # set fresh dataset base path (directory containing .dat files)
        fresh_dataset_dir = os.path.join(dataset_dir, 'fresh_dataset')

        # if the fresh dataset is not present, generate it
        if not fresh_check_files(fresh_dataset_dir):
            logger.info("Fresh dataset not found.")

            # generate fresh dataset
            build_fresh_dataset_run = run("build_fresh_dataset", {
                'dataset_dest_dir': fresh_dataset_dir
            }, config_sha=fresh_eval_config_sha)

        # for each training run
        for training_run_id in range(runs):
            logger.info("initiating training run n. {}".format(str(training_run_id)))

            # create family classifier from previously trained network and train it on fresh dataset
            f_c_train_run = get_or_run("train_family_classifier", {
                'fresh_ds_path': fresh_dataset_dir,
                'epochs': f_c_epochs,
                'training_run': training_run_id,
                'train_split_proportion': f_c_train_split_proportion,
                'valid_split_proportion': f_c_valid_split_proportion,
                'test_split_proportion': f_c_test_split_proportion,
                'batch_size': f_c_batch_size
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=family_class_config_sha)

            # get model checkpoints path
            f_c_checkpoint_path = parse.unquote(parse.urlparse(os.path.join(f_c_train_run.info.artifact_uri,
                                                                            "model_checkpoints")).path)

            # set model checkpoint filename
            f_c_checkpoint_file = os.path.join(f_c_checkpoint_path, "epoch_{}.pt".format(f_c_epochs))

            # evaluate model against fresh dataset
            f_c_eval_run = get_or_run("evaluate_family_classifier", {
                'fresh_ds_path': fresh_dataset_dir,
                'checkpoint_path': f_c_checkpoint_file,
                'training_run': training_run_id,
                'train_split_proportion': f_c_train_split_proportion,
                'valid_split_proportion': f_c_valid_split_proportion,
                'test_split_proportion': f_c_test_split_proportion,
                'batch_size': f_c_batch_size
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=family_class_config_sha)

            # get model evaluation results path
            f_c_results_path = parse.unquote(parse.urlparse(os.path.join(f_c_eval_run.info.artifact_uri,
                                                                         "family_class_results")).path)

            # set model evaluation results filename
            f_c_results_file = os.path.join(f_c_results_path, "results.csv")

            # compute (and plot) all tagging results
            f_c_compute_results_run = get_or_run("compute_all_family_class_results", {
                'results_file': f_c_results_file,
                'fresh_ds_path': fresh_dataset_dir
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=family_class_config_sha)


@baker.command
def contrastive_learning_only(base_dir,  # base tool path
                              use_cache=1,  # whether to skip already executed runs (in cache) or not (1/0)
                              ignore_git=0):  # whether to ignore git version or not (1/0)
    """ Automatic Malware Signature Generation MLflow workflow.

    Args:
        base_dir: Base tool path
        use_cache: Whether to skip already executed runs (in cache) or not (1/0)
        ignore_git: Whether to ignore git version or not (1/0)
    """

    # get some needed variables from config file
    runs = int(config['general']['runs'])
    net_type = 'mtje'

    training_n_samples = int(config['sorel20mDataset']['training_n_samples'])
    validation_n_samples = int(config['sorel20mDataset']['validation_n_samples'])
    test_n_samples = int(config['sorel20mDataset']['test_n_samples'])

    c_l_epochs = int(config['contrastiveLearning']['epochs'])
    c_l_train_split_proportion = int(config['contrastiveLearning']['train_split_proportion'])
    c_l_valid_split_proportion = int(config['contrastiveLearning']['valid_split_proportion'])
    c_l_test_split_proportion = int(config['contrastiveLearning']['test_split_proportion'])
    c_l_batch_size = int(config['contrastiveLearning']['batch_size'])
    c_l_rank_size = int(config['contrastiveLearning']['rank_size'])
    c_l_knn_k_min = int(config['contrastiveLearning']['knn_k_min'])
    c_l_knn_k_max = int(config['contrastiveLearning']['knn_k_max'])

    # initialize Hash object
    ch = Hash()
    # update hash with the content of the config file (for the current net type)
    ch.update(json.dumps(dict(config.items(net_type))))
    # update hash with the content of the config file (for the freshDataset)
    ch.update(json.dumps(dict(config.items('freshDataset'))))
    # get config file sha256 digest
    fresh_eval_config_sha = ch.get_b64()

    # update hash with the content of the config file (for the freshDataset)
    ch.update(json.dumps(dict(config.items('contrastiveLearning'))))
    # get config file sha256 digest
    contr_learn_config_sha = ch.get_b64()

    # Note: The entrypoint names are defined in MLproject. The artifact directories
    # are documented by each step's .py file.

    # start mlflow run
    with mlflow.start_run() as active_run:
        # get code git commit version
        git_commit = active_run.data.tags.get(mlflow_tags.MLFLOW_GIT_COMMIT)

        # log config file
        mlflow.log_text(json.dumps({s: dict(config.items(s)) for s in config.sections()}), 'config.txt')

        # set dataset destination dir
        dataset_dir = os.path.join(base_dir, 'dataset')
        # set fresh dataset base path (directory containing .dat files)
        fresh_dataset_dir = os.path.join(dataset_dir, 'fresh_dataset')

        # if the fresh dataset is not present, generate it
        if not fresh_check_files(fresh_dataset_dir):
            logger.info("Fresh dataset not found.")

            # generate fresh dataset
            build_fresh_dataset_run = run("build_fresh_dataset", {
                'dataset_dest_dir': fresh_dataset_dir
            }, config_sha=fresh_eval_config_sha)

        c_l_results_files = {}

        # for each training run
        for training_run_id in range(runs):
            logger.info("initiating training run n. {}".format(str(training_run_id)))

            # create family classifier from previously trained network and train it on fresh dataset
            c_l_train_run = get_or_run("train_contrastive_net", {
                'fresh_ds_path': fresh_dataset_dir,
                'epochs': c_l_epochs,
                'training_run': training_run_id,
                'train_split_proportion': c_l_train_split_proportion,
                'valid_split_proportion': c_l_valid_split_proportion,
                'test_split_proportion': c_l_test_split_proportion,
                'batch_size': c_l_batch_size
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=contr_learn_config_sha)

            # get model checkpoints path
            c_l_checkpoint_path = parse.unquote(parse.urlparse(os.path.join(c_l_train_run.info.artifact_uri,
                                                                            "model_checkpoints")).path)

            # set model checkpoint filename
            c_l_checkpoint_file = os.path.join(c_l_checkpoint_path, "epoch_{}.pt".format(c_l_epochs))

            # evaluate model against fresh dataset
            c_l_eval_run = get_or_run("evaluate_contrastive_net", {
                'fresh_ds_path': fresh_dataset_dir,
                'checkpoint_path': c_l_checkpoint_file,
                'training_run': training_run_id,
                'train_split_proportion': c_l_train_split_proportion,
                'valid_split_proportion': c_l_valid_split_proportion,
                'test_split_proportion': c_l_test_split_proportion,
                'batch_size': c_l_batch_size,
                'rank_size': c_l_rank_size,
                'knn_k_min': c_l_knn_k_min,
                'knn_k_max': c_l_knn_k_max
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=contr_learn_config_sha)

            # get model evaluation results path
            c_l_results_path = parse.unquote(parse.urlparse(os.path.join(c_l_eval_run.info.artifact_uri,
                                                                         "contrastive_learning_results")).path)

            # set model evaluation results filename
            c_l_results_file = os.path.join(c_l_results_path, "results.csv")

            # compute (and plot) all contrastive model results
            c_l_compute_results_run = get_or_run("compute_contrastive_learning_results", {
                'results_file': c_l_results_file,
                'fresh_ds_path': fresh_dataset_dir,
                'knn_k_min': c_l_knn_k_min,
                'knn_k_max': c_l_knn_k_max
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=contr_learn_config_sha)

            # get model evaluation results path
            c_l_scores_dir_path = parse.unquote(parse.urlparse(os.path.join(c_l_compute_results_run.info.artifact_uri,
                                                                            "contrastive_learning_scores")).path)

            # add dir path to c_l_results_files dictionary (used for plotting mean score trends)
            c_l_results_files["run_id_" + str(training_run_id)] = c_l_scores_dir_path

        # create contrastive learning temp dir name using the value from config_sha (sha of some parts of the config
        # file). -> This is done in order to have a different (but predictable) run_to_filename at each set of runs with
        # different parameters. This allows mlflow to know when it is needed to run 'per_tag_plot_runs'. If, on the
        # other hand a simple tempfile.TemporaryDirectory() was used then mlflow would run 'per_tag_plot_runs' every
        # time, even if a precedent run was available (because the parameter 'run_to_filename_json' would be different)
        c_l_tempdir = os.path.join(base_dir, 'tmp_{}'.format(contr_learn_config_sha))
        # create temp dir
        os.makedirs(c_l_tempdir, exist_ok=True)

        # set run-to-filename file path
        c_l_run_to_filename = os.path.join(c_l_tempdir, "c_l_results.json")

        # create and open the c_l_results.json file in write mode
        with open(c_l_run_to_filename, "w") as output_file:
            # save c_l_results_files dictionary as a json file
            json.dump(c_l_results_files, output_file)

        mlflow.log_artifact(c_l_run_to_filename, "run_to_filename")

        # if there is more than 1 run, compute also the model mean scores trends
        if runs > 1:
            # plot all model mean scores trends
            plot_all_scores_trends = get_or_run("plot_all_scores_trends", {
                'run_to_filename_json': c_l_run_to_filename,
                'knn_k_min': c_l_knn_k_min,
                'knn_k_max': c_l_knn_k_max
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=contr_learn_config_sha)

        # remove contrastive learning temp files and temporary directory
        os.remove(c_l_run_to_filename)
        # os.remove(fresh_run_to_filename)
        os.rmdir(c_l_tempdir)


if __name__ == "__main__":
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
