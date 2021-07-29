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
    runs = int(config['jointEmbedding']['runs'])
    workers = int(config['general']['workers'])
    batch_size = int(config['jointEmbedding']['batch_size'])
    epochs = int(config['jointEmbedding']['epochs'])
    use_malicious_labels = int(config['jointEmbedding']['use_malicious_labels'])
    use_count_labels = int(config['jointEmbedding']['use_count_labels'])
    gen_type = config['jointEmbedding']['gen_type']
    similarity_measure = config['jointEmbedding']['similarity_measure'].lower()
    net_type = 'jointEmbedding'

    training_n_samples = int(config['sorel20mDataset']['training_n_samples'])
    validation_n_samples = int(config['sorel20mDataset']['validation_n_samples'])
    test_n_samples = int(config['sorel20mDataset']['test_n_samples'])

    min_n_anchor_samples = int(config['freshDataset']['min_n_anchor_samples'])
    max_n_anchor_samples = int(config['freshDataset']['max_n_anchor_samples'])
    fresh_n_queries = int(config['freshDataset']['n_queries'])
    n_evaluations = int(config['freshDataset']['n_evaluations'])

    refine_epochs = int(config['refineModel']['epochs'])
    refine_train_split_proportion = int(config['refineModel']['train_split_proportion'])
    refine_valid_split_proportion = int(config['refineModel']['valid_split_proportion'])
    refine_test_split_proportion = int(config['refineModel']['test_split_proportion'])
    refine_batch_size = int(config['refineModel']['batch_size'])

    # initialize Hash object
    ch = Hash()
    # update hash with the content of the config file (for the current net type)
    ch.update(json.dumps(dict(config.items(net_type))))
    # get config file sha256 digest
    config_sha = ch.get_b64()

    # update hash with the content of the config file (for the freshDataset)
    ch.update(json.dumps(dict(config.items('freshDataset'))))
    # get config file sha256 digest
    fresh_eval_config_sha = ch.get_b64()

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
                }, config_sha=config_sha)

            # pre-process dataset
            preprocess_dataset_run = run("preprocess_dataset", {
                'ds_path': dataset_base_path,
                'destination_dir': pre_processed_dataset_dir,
                'training_n_samples': training_n_samples,
                'validation_n_samples': validation_n_samples,
                'test_n_samples': test_n_samples,
                'batch_size': batch_size,
                'remove_missing_features': str(os.path.join(dataset_base_path, "shas_missing_ember_features.json"))
            }, config_sha=config_sha)

        # if the fresh dataset is not present, generate it
        if not fresh_check_files(fresh_dataset_dir):
            logger.info("Fresh dataset not found.")

            # generate fresh dataset
            build_fresh_dataset_run = run("build_fresh_dataset", {
                'dataset_dest_dir': fresh_dataset_dir
            }, config_sha=config_sha)

        # initialize results files dicts
        results_files = {}
        refined_results_files = {}

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

            # evaluate model against fresh dataset
            fresh_evaluation_run = get_or_run("evaluate_fresh", {
                'fresh_ds_path': fresh_dataset_dir,
                'checkpoint_path': checkpoint_file,
                'net_type': net_type if similarity_measure == 'dot' else net_type + '_{}'.format(similarity_measure),
                'min_n_anchor_samples': min_n_anchor_samples,
                'max_n_anchor_samples': max_n_anchor_samples,
                'n_query_samples': fresh_n_queries,
                'n_evaluations': n_evaluations
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=fresh_eval_config_sha)

            # get model evaluation results path
            fresh_results_path = parse.unquote(parse.urlparse(os.path.join(fresh_evaluation_run.info.artifact_uri,
                                                                           "fresh_prediction_results")).path)

            # set model evaluation results filename
            fresh_results_file = os.path.join(fresh_results_path, "fresh_prediction_results.json")

            # compute (and plot) all family prediction results (on fresh dataset)
            all_tagging_results_run = get_or_run("compute_all_run_fresh_results", {
                'results_file': fresh_results_file
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=fresh_eval_config_sha)

            # evaluate model against fresh dataset
            model_refine_run = get_or_run("refine", {
                'fresh_ds_path': fresh_dataset_dir,
                'checkpoint_path': checkpoint_file,
                'epochs': refine_epochs,
                'train_split_proportion': refine_train_split_proportion,
                'valid_split_proportion': refine_valid_split_proportion,
                'test_split_proportion': refine_test_split_proportion,
                'batch_size': refine_batch_size
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=fresh_eval_config_sha)

            # get model evaluation results path
            refined_results_path = parse.unquote(parse.urlparse(os.path.join(model_refine_run.info.artifact_uri,
                                                                             "refined_model_results")).path)

            # set model evaluation results filename
            refined_results_file = os.path.join(refined_results_path, "refined_results.csv")

            # add file path to results_files dictionary (used for plotting mean results)
            refined_results_files["run_id_" + str(training_run_id)] = refined_results_file

            # compute (and plot) all tagging results
            refined_model_compute_results_run = get_or_run("compute_all_refined_results", {
                'results_file': results_file,
                'fresh_ds_path': fresh_dataset_dir
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=config_sha)

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
        # create temp dir
        os.makedirs(tempdir, exist_ok=True)

        # set run-to-filename file path
        run_to_filename = os.path.join(tempdir, "results.json")
        # fresh_run_to_filename = os.path.join(tempdir, "fresh_results.json")

        # create and open the results.json file in write mode
        with open(run_to_filename, "w") as output_file:
            # save results_files dictionary as a json file
            json.dump(results_files, output_file)

        # # create and open the fresh_results.json file in write mode
        # with open(fresh_run_to_filename, "w") as output_file:
        #     # save fresh_results_files dictionary as a json file
        #     json.dump(fresh_results_files, output_file)

        mlflow.log_artifact(run_to_filename, "run_to_filename")
        # mlflow.log_artifact(fresh_run_to_filename, "fresh_run_to_filename")

        # if there is more than 1 run, compute also per-tag mean results
        if runs > 1:
            # plot all roc distributions
            per_tag_plot_runs = get_or_run("plot_all_roc_distributions", {
                'run_to_filename_json': run_to_filename,
                'use_malicious_labels': use_malicious_labels,
                'use_tag_labels': 1
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=config_sha)

            # # plot all roc distributions
            # per_family_plot_runs = get_or_run("plot_all_fresh_roc_distributions", {
            #     'run_to_filename_json': fresh_run_to_filename,
            #     'ds_path': fresh_dataset_dir
            # }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=fresh_eval_config_sha)

        # remove temp files and temporary directory
        os.remove(run_to_filename)
        # os.remove(fresh_run_to_filename)
        os.rmdir(tempdir)


@baker.command
def detection_workflow(base_dir,  # base tool path
                       use_cache=1,  # whether to skip already executed runs (in cache) or not (1/0)
                       ignore_git=0):  # whether to ignore git version or not (1/0)
    """ Base detection MLflow workflow.

    Args:
        base_dir: Base tool path
        use_cache: Whether to skip already executed runs (in cache) or not (1/0)
        ignore_git: Whether to ignore git version or not (1/0)
    """

    # get some needed variables from config file
    runs = int(config['detectionBase']['runs'])
    workers = int(config['general']['workers'])
    batch_size = int(config['detectionBase']['batch_size'])
    epochs = int(config['detectionBase']['epochs'])
    use_malicious_labels = int(config['detectionBase']['use_malicious_labels'])
    use_count_labels = int(config['detectionBase']['use_count_labels'])
    use_tag_labels = int(config['detectionBase']['use_tag_labels'])
    gen_type = config['detectionBase']['gen_type']
    net_type = 'detectionBase'

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
    ch.update(json.dumps(dict(config.items(net_type))))
    # get config file sha256 digest
    config_sha = ch.get_b64()

    # update hash with the content of the config file (for the freshDataset)
    ch.update(json.dumps(dict(config.items('freshDataset'))))
    # get config file sha256 digest
    fresh_eval_config_sha = ch.get_b64()

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
                }, config_sha=config_sha)

            # pre-process dataset
            preprocess_dataset_run = run("preprocess_dataset", {
                'ds_path': dataset_base_path,
                'destination_dir': pre_processed_dataset_dir,
                'training_n_samples': training_n_samples,
                'validation_n_samples': validation_n_samples,
                'test_n_samples': test_n_samples,
                'batch_size': batch_size,
                'remove_missing_features': str(os.path.join(dataset_base_path, "shas_missing_ember_features.json"))
            }, config_sha=config_sha)

        results_files = {}
        fresh_results_files = {}
        fresh_features_results_files ={}

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
                'ds_path': fresh_dataset_dir,
                'checkpoint_path': checkpoint_file,
                'net_type': net_type,
                'min_n_anchor_samples': min_n_anchor_samples,
                'max_n_anchor_samples': max_n_anchor_samples,
                'n_query_samples': fresh_n_queries,
                'n_evaluations': n_evaluations
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=fresh_eval_config_sha)

            # get model evaluation results path
            fresh_results_path = parse.unquote(parse.urlparse(os.path.join(fresh_evaluation_run.info.artifact_uri,
                                                                           "fresh_prediction_results")).path)

            # set model evaluation results filename
            fresh_features_results_file = os.path.join(fresh_results_path, "fresh_features_prediction_results.json")
            # set model evaluation results filename
            fresh_results_file = os.path.join(fresh_results_path, "fresh_prediction_results.json")

            # add file path to results_files dictionary (used for plotting mean results)
            fresh_features_results_files["run_id_" + str(training_run_id)] = fresh_features_results_file
            # add file path to results_files dictionary (used for plotting mean results)
            fresh_results_files["run_id_" + str(training_run_id)] = fresh_results_file

            # compute (and plot) all family prediction results (on fresh dataset)
            all_tagging_results_run = get_or_run("compute_all_run_fresh_results", {
                'results_file': fresh_features_results_file
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=fresh_eval_config_sha)

            # compute (and plot) all family prediction results (on fresh dataset)
            all_tagging_results_run = get_or_run("compute_all_run_fresh_results", {
                'results_file': fresh_results_file
            }, git_commit, ignore_git=bool(ignore_git), use_cache=bool(use_cache), config_sha=fresh_eval_config_sha)

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


if __name__ == "__main__":
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
