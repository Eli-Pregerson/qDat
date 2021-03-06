"""The main implementation of the REPL."""
from __future__ import annotations
import copy
import os.path
import random
import re
import readline
import subprocess
import tempfile
import time
import csv
from collections import defaultdict
from enum import Enum
from functools import partial
from multiprocessing import Manager, Pool, Lock
from os import getpid, listdir  # pylint: disable=unused-import
from pathlib import Path
from queue import Queue
from typing import Iterable, Optional, Union, cast
from pandas import read_csv

import numpy  # type: ignore
from rich.console import Console
from rich.table import Table

from core.command_data import AnyDict, Data, MetricRes, ObjTypes, PathComplexityRes
from core.env import KnownExtensions
from core.error_messages import (EXTENSION, MISSING_FILENAME, MISSING_NAME, MISSING_TYPE_AND_NAME,
                                 NO_FILE_EXT, ReplErrors)
from core.log import Colors, Log, LogLevel
from experiments.data_collection import DataCollector

from graph.control_flow_graph import ControlFlowGraph
from inlining import inlining_script, inlining_script_heuristic
from klee.klee_utils import KleeUtils
from lang_to_cfg import converter, cpp, java, python
from metric import cyclomatic_complexity, loc, metric, npath_complexity, path_complexity
from utils import Timeout

# Temporarily disable unused arguments due to flags.
# pylint: disable=unused-argument

class InlineType(Enum):
    """Possible ways to work with inline functions in convert."""

    Inline = partial(inlining_script.in_lining)
    Heuristic = partial(inlining_script_heuristic.in_lining)


class Controller:
    """Store the file extension we know how to generate graphs for and the generators."""

    def __init__(self, logger: Log) -> None:
        """
        Create a new instance of Controller by initializing all of the converters.

        The converters turn known file types into CFGS.
        """
        self.logger = logger

        cyclomatic = cyclomatic_complexity.CyclomaticComplexity(self.logger)
        npath = npath_complexity.NPathComplexity(self.logger)
        pathcomplexity = path_complexity.PathComplexity(self.logger)
        locs = loc.LinesOfCode(self.logger)

        self.metrics_generators: list[metric.MetricAbstract] = [cyclomatic, npath,
                                                                pathcomplexity, locs]

        cpp_converter = cpp.CPPConvert(self.logger)
        java_converter = java.JavaConvert(self.logger)
        python_converter = python.PythonConvert(self.logger)
        self.graph_generators = {
            ".cpp": cpp_converter,
            ".c": cpp_converter,
            ".jar": java_converter,
            ".class": java_converter,
            ".java": java_converter,
            ".py": python_converter,
        }

    def get_graph_generator_names(self) -> Iterable[str]:
        """Get the names of all file extensions we know how to generate CFGs for."""
        return self.graph_generators.keys()

    def get_graph_generator(self, file_extension: str) -> converter.ConverterAbstract:
        """Given a file extension as a string, return the CFG generator for that file extension."""
        return self.graph_generators[file_extension]


def multiprocess_import(shared_dict: dict[str, ControlFlowGraph], file: str) -> None:
    """Handle the multiprocessing of import."""
    graph = ControlFlowGraph.from_file(file)
    if isinstance(graph, dict):
        shared_dict.update(graph)
    else:
        filepath, _ = os.path.splitext(file)
        shared_dict[filepath] = graph

def multiprocess_metrics(
    metrics_generators: dict[str, metric.MetricAbstract],
    shared_dict: dict[tuple[str, str], Union[int, PathComplexityRes]],
    queue: Queue[ControlFlowGraph],
    lock: Lock,
    process_count: int) -> None:
    """Handle the multiprocessing of metrics."""
    print(f"Starting {process_count}")
    while True:
        with lock:
            if not queue.empty():
                graph, generator_name = queue.get()
            else:
                break
        metrics_generator = metrics_generators[generator_name]
        timeout = 1200 if metrics_generator.name() == "Path Complexity" else 180
        try:
            if metrics_generator.name() == "Lines of Code" and \
            graph.metadata.language is not KnownExtensions.Python:
                continue
            # print(f"Getting {metrics_generator.name()} for graph {graph.name} on process {os.getpid()}.")
            with Timeout(timeout, "Took too long!"):
                result = metrics_generator.evaluate(graph)

            if graph.name is None:
                raise ValueError("No Graph name.")

            shared_dict[(graph.name, metrics_generator.name())] = result
        except IndexError as err:
            print(graph)
            print(err)
        except TimeoutError as err:
            print(err, graph.name, metrics_generator.name())
            shared_dict[(graph.name, metrics_generator.name())] = ("NA", "Timeout")
    print(f"Queue {process_count} is done.")

class REPLOptions():
    """Contains options for the REPL such as debug mode."""

    curr_path: str
    debug_mode: bool
    rich: bool
    multithreaded: bool

    def __init__(self, curr_path: str, debug_mode: bool, poor: bool, multithreaded: bool = False) -> None:
        """Initialize information about the REPL."""
        self.curr_path = curr_path
        self.debug_mode = debug_mode
        self.rich = not poor
        self.multithreaded = multithreaded

    def get_curr_path(self) -> str:
        """Return the current path."""
        return self.curr_path

    def get_debug_mode(self) -> bool:
        """Return whether or not the REPL should be initialized in debug mode."""
        return self.debug_mode

    def get_rich(self) -> bool:
        """Return whether or not the REPL should be initialized with rich enabled."""
        return self.rich

    def get_multithreaded(self) -> bool:
        """Return whether or not the REPL should be initialized in multithreading mode."""
        return self.multithreaded


class CmdInfo:
    """Information about the arguments to a REPL command."""

    num_args: int
    err: str
    check_recursive: bool
    var_args: bool

    def __init__(self, num_args: int, err: str, check_recursive: bool = False, var_args: bool = False) -> None:
        """Initialize information about a command."""
        self.num_args = num_args
        self.err = err
        self.check_recursive = check_recursive
        self.var_args = var_args

    def get_num_args(self) -> int:
        """Return the number of arguments."""
        return self.num_args

    def get_err(self) -> str:
        """Return the error message."""
        return self.err

    def get_recursive(self) -> bool:
        """Return whether the command has a recursive mode."""
        return self.check_recursive

    def get_var_args(self) -> bool:
        """Return whether the command accepts a variable number of arguments."""
        return self.var_args


class Options:
    """Information about the REPL commands and their arguments."""

    commands: dict[str, CmdInfo] = {
        "to_klee_format": CmdInfo(1, MISSING_FILENAME, True),
        "klee_to_bc": CmdInfo(1, ReplErrors.KLEE_FORMATTED),
        "klee": CmdInfo(1, ReplErrors.KLEE_FORMATTED, False, True),
        "klee_replay": CmdInfo(1, MISSING_FILENAME),
        "import": CmdInfo(1, MISSING_FILENAME, True, True),
        "list": CmdInfo(1, ReplErrors.TYPE_TO_LIST),
        "show": CmdInfo(2, ReplErrors.SPECIFY_TYPE),
        "metrics": CmdInfo(1, ReplErrors.GRAPH_NAME),
        "vector": CmdInfo(0, ReplErrors.GRAPH_NAME),
        "delete": CmdInfo(2, MISSING_TYPE_AND_NAME),
        "export": CmdInfo(2, MISSING_TYPE_AND_NAME),
        "run_experiment": CmdInfo(2, MISSING_FILENAME),
        "quit": CmdInfo(0, ReplErrors.NO_ARGS),
        "cd": CmdInfo(1, MISSING_NAME),
        "ls": CmdInfo(0, ReplErrors.CANNOT_ACCEPT_ARGS),
        "mv": CmdInfo(2, ReplErrors.MISSING_NAMES_MV),
        "rm": CmdInfo(1, ReplErrors.MISSING_PATH_RM, True, True),
        "mkdir": CmdInfo(1, ReplErrors.MISSING_NAME_MKDIR),
        "pwd": CmdInfo(0, ReplErrors.CANNOT_ACCEPT_ARGS)
    }

    def __init__(self, recursive_mode: bool = False, graph_stitching: bool = False,
                 inlining: bool = False, heuristic_inlining: bool = False) -> None:
        """Create a new set of flags to pass in to a command."""
        self.recursive_mode = recursive_mode
        self.graph_stitching = graph_stitching
        self.inlining = inlining
        self.heuristic_inlining = heuristic_inlining


class Command:
    # pylint: disable=R0904
    """Command is the implementation of the REPL commands."""

    def __init__(self, options: REPLOptions, repl_wrapper: object) -> None:
        """Create a new instance of the REPL implementation."""
        if options.get_debug_mode():
            self.logger = Log(log_level=LogLevel.DEBUG)
        else:
            self.logger = Log(log_level=LogLevel.REGULAR)

        self.logger.d_msg("Debug Mode Enabled")
        if options.get_multithreaded():
            self.logger.i_msg("Multithreading Enabled")
        self.multi_threaded = options.get_multithreaded()
        self.controller = Controller(self.logger)
        self._klee_utils = KleeUtils(self.logger)
        self.rich = options.get_rich()
        self.data = Data(self.logger, self.rich)
        self._repl_wrapper = repl_wrapper
        self.curr_path = options.get_curr_path()
        self.debug_mode = options.get_debug_mode()

    def verify_file_type(self, args: str, target_type: str) -> Optional[str]:
        """
        Verify that the file extension for the file passed in matches the expected file type.

        The input is the set of arguments passed in to the REPL by the user converted into a
        list.
        """
        _, file_extension = os.path.splitext(args[0])
        if file_extension == "":
            self.logger.v_msg(NO_FILE_EXT(args[0]))
            return None

        if file_extension.strip() != f".{target_type}":
            self.logger.v_msg(EXTENSION(target_type, file_extension))
            return None

        return args[0]

    def do_run_experiment(self, flags: Options, input_path: str, output_path: str) -> None:
        """Convert and compute metrics for all files in the input directory and store all of the data in a csv."""
        files = self.get_files(input_path, True, list(self.controller.graph_generators.keys()))
        collector = DataCollector(self.logger, input_path, output_path)
        collector.collect(files)
        self.logger.v_msg(f"Results written to {output_path}.csv")

    def do_klee_replay(self, flags: Options, file_name: str) -> None:
        """
        Execute a test generated by KLEE given a klee test file.

        Usage:
        klee_replay <file>
        """
        if (result := self.verify_file_type(file_name, "ktest")) is None:
            return

        path_to_klee_build_dir = '/app/build'
        command_one = 'export LD_LIBRARY_PATH={path_to_klee_build_dir}/lib/:$LD_LIBRARY_PATH'
        command_two = "gcc -I ../../include -L path-to-klee-build-dir/lib/ get_sign.c -lkleeRuntest"

        self.logger.d_msg(path_to_klee_build_dir, command_one, command_two, result)

    def get_files(self, path: str, recursive_mode: bool, allowed_extensions: list[str]) -> list[str]:
        """
        get_files returns a list of files from the given path.

        If the path is a file, it returns a singleton containing the file.
        Otherwise, it returns all of the files in the current directory.
        If it is not a valid path, return no files.
        """
        abspath = path
        if not os.path.isabs(path):
            abspath = os.path.join(self.curr_path, path)

        self.logger.d_msg(f"Looking for files given path {path}")
        if os.path.isfile(abspath):
            self.logger.d_msg(f"{abspath} is a file.")
            if recursive_mode:
                self.logger.v_msg("Cannot use recursive mode with filename.")
                return []

            return [abspath]

        if os.path.isdir(abspath):
            self.logger.d_msg(f"{abspath} is a directory")
            if recursive_mode:
                all_files: list[Path] = []
                for extension in allowed_extensions:
                    all_files += Path(abspath).rglob(f"*{extension}")

                return [str(file) for file in all_files]

            # Get all of the files in this directory.
            return [f for f in listdir(abspath) if os.path.isfile(os.path.join(abspath, f))]

        self.logger.d_msg("Checking if it's a regular expression")
        # Check if it's a regular expression (only allowed at the END of the filename).
        original_base, file = os.path.split(path)
        self.logger.d_msg(f"base: {original_base} file: {file}")

        return self.get_files_from_regex(file, original_base, recursive_mode)

    def get_files_from_regex(self, input_file: str,
                             original_base: str, recursive_mode: bool) -> list[str]:
        """Try to compile a path as a regular expression and get the matching files."""
        try:
            regexp = re.compile(input_file)
            self.logger.d_msg("Successfully compiled as a regular expression")
            all_files: list[str] = []
            if os.path.exists(original_base):
                if recursive_mode:
                    # Get all files in all subdirectories.
                    file_list = list(Path(original_base).rglob("*"))
                    all_files += [str(file_path) for file_path in file_list]
                else:
                    all_files = [f for f in listdir(original_base) if
                                 os.path.isfile(os.path.join(original_base, f))]

                matched_files = []
                for file in all_files:
                    name = os.path.split(file)[1]
                    if regexp.match(name):
                        matched_files.append(os.path.join(original_base, file))

                return matched_files

            return []
        except re.error:
            # Try checking for just wildcard operators.
            self.logger.d_msg("Checking for wildcard operators")
            input_file = input_file.replace(".", r"\.")
            input_file = input_file.replace("*", ".*")
            try:
                regexp = re.compile(input_file)
                self.logger.d_msg("Successfully compiled as a regular expression")
                if os.path.exists(original_base):
                    all_files = [f for f in listdir(original_base) if
                                 os.path.isfile(os.path.join(original_base, f))]
                    matched_files = []
                    for file in all_files:
                        name = os.path.split(file)[1]
                        if regexp.match(name):
                            matched_files.append(os.path.join(original_base, file))

                    return matched_files

            except re.error:
                pass

            return []

    def parse_convert_args(self, arguments: list[str]) -> tuple[list[str], bool,
                                                                Optional[InlineType], bool]:
        """Parse the command line arguments for the convert command."""
        recursive_mode = False
        inline_type = None
        graph_stitching = False

        if len(arguments) > 0:
            if arguments[0] == ("-r" or "--recursive"):
                recursive_mode = True
                args_list = arguments[1:]
            elif arguments[0] == ("-i" or "--inline_functions"):
                inline_type = InlineType.Inline
                args_list = arguments[1:]
            elif arguments[0] == ("-h" or "--heuristic_inline"):
                if inline_type is InlineType.Inline:
                    err_msg = "Can't use inline and heuristic inline at the same time! " + \
                              "Defaulting to basic inline."
                    self.logger.v_msg(err_msg)
                    inline_type = None
                else:
                    inline_type = InlineType.Heuristic
                args_list = arguments[1:]
            elif arguments[0] == ("-gs" or "--graph_stitch"):
                graph_stitching = True
                args_list = arguments[1:]
            else:
                args_list = arguments

            return args_list, recursive_mode, inline_type, graph_stitching

        self.logger.v_msg("Not enough arguments!")
        return [], False, inline_type, graph_stitching

    def do_convert(self, args: str) -> None:  # pylint: disable=too-many-branches
        """
        Convert a file containing source code to a Graph object.
        The recursive flag (-r) can also be used.
        Usage:
        convert <file-like>
        convert -r <file-like>
        convert <file-like-1> <file-like-2> ... <file-like-n>
        """
        # Iterate through all file-like objects.
        # prints out the arguments such as -r experiments/Jmol/version2/classes
        print(args)
        arguments = args.split(" ")
        args_list, recursive_mode, inline_type, graph_stitching = self.parse_convert_args(arguments)
        if len(args_list) == 0:
            self.logger.v_msg("Not enough arguments!")
            return

        all_files: list[str] = []
        for full_path in args_list:
            files = self.get_files(full_path, recursive_mode, list(self.controller.graph_generators.keys()))
            if files == []:
                self.logger.e_msg(f"Could not get files from: {full_path}")
                return

            all_files += files

        self.logger.d_msg(f"Convert files {all_files}")
        # Make sure files are valid (if using recursive mode
        # this is done automatically in the previous step).

        for file in all_files:
            file = str(file)  # used for typechecking.
            self.logger.d_msg(f"Looking at file {file}")
            filepath, file_extension = os.path.splitext(file)
            if file_extension not in self.controller.get_graph_generator_names():
                if file_extension == "":
                    self.logger.v_msg(NO_FILE_EXT(file))
                else:
                    self.logger.v_msg(f"Cannot convert {file_extension} for {file}.")
                return

            if inline_type is not None:
                self.logger.v_msg(f"Converting {file}")
                inline_type.value(file)
                filepath = os.path.splitext(file.split('.')[0] + "-auto-inline.c")[0]

            converter_inst = self.controller.get_graph_generator(file_extension)
            graph = converter_inst.to_graph(filepath.strip(), file_extension.strip())
            if graph is None:
                self.logger.i_msg("Conversion Failed. Maybe your code has an error?")
            else:
                self.logger.i_msg("Converted successfully")
                self.logger.d_msg(str(graph))
                # checks if a graph is a dictionary 
                if isinstance(graph, dict):
                    if graph == {}:
                        self.logger.v_msg("Converted without errors, but no graphs created.")
                    else:
                        self.logger.v_msg(f"Created graph objects {Colors.MAGENTA.value}"
                                          f"{' '.join(list(graph.keys()))}{Colors.ENDC.value}")
                        # the update metod takes a dictionary (graph) and updates the dictionary with elements
                        # from a dictionary object. It doesn't return any value. self.data.graphs is a dictionary which has the method name
                        # as a key and value as the graph object 
                        self.data.graphs.update(graph)
                # checks if a graph is a ControlFlowGraph
                elif isinstance(graph, ControlFlowGraph):
                    self.logger.v_msg(f"Created graph {graph.name}")
                    self.data.graphs[filepath] = graph
                if graph_stitching:
                    main = ControlFlowGraph.stitch(copy.deepcopy(graph))
                    main.name  = os.path.basename(filepath) + "-full"
                    self.logger.v_msg(f"Created stitched graph {main.name}")
                    self.data.graphs[main.name] = main
                    

    def do_import(self, flags: Options, *args_list: str) -> None:
        """
        Convert a .dot file representing a cfg into a Graph object.

        The recursive flag (-r) can also be used.

        Usage:
        import <file-like>
        import -r <file-like>
        import <file-like-1> <file-like-2> ... <file-like-n>
        """
        # Iterate through all file-like objects.
        all_files = []
        allowed_extensions = ["dot"]
        for full_path in args_list:
            files = self.get_files(full_path, flags.recursive_mode, allowed_extensions)
            if files == []:
                self.logger.v_msg(f"Could not get files from: {full_path}")
                return
            all_files += files

        self.logger.d_msg(f"Convert {all_files}")
        # Make sure files are valid (if using recursive mode
        #  this is done automatically in the previous step).
        if self.multi_threaded:
            manager = Manager()
            shared_dict: dict[str, ControlFlowGraph] = manager.dict()
            pool = Pool(8)
            pool.map(partial(multiprocess_import, shared_dict), all_files)
            self.logger.v_msg(f"Created graph objects "
                              f"{Colors.MAGENTA.value}{' '.join(shared_dict.keys())}{Colors.ENDC.value}")
            self.data.graphs.update(shared_dict)
        else:
            graphs = []
            for file in all_files:
                filepath, _ = os.path.splitext(file)
                graph = ControlFlowGraph.from_file(file)
                graphs.append(graph)
                self.data.graphs[filepath] = graph
            names = [graph.name for graph in graphs]
            self.logger.v_msg(f"Created graph objects "
                              f"{Colors.MAGENTA.value}{' '.join(names)}{Colors.ENDC.value}")

    def do_list(self, flags: Options, list_typename: str) -> None:
        """
        List all of the objects of a specific type (metrics, graphs, or a KLEE type).

        Usage:
        list <metrics/graphs/KLEE type>
        list *
        """
        list_type = ObjTypes.get_type(list_typename)
        if list_type is None:
            self.logger.e_msg("Unrecognized type.")
            return

        if list_type == ObjTypes.METRIC:
            self.data.list_metrics()
        elif list_type == ObjTypes.GRAPH:
            self.data.list_graphs()
        elif list_type == ObjTypes.KLEE_BC:
            self.data.list_klee_bc()
        elif list_type == ObjTypes.KLEE_STATS:
            self.data.list_klee_stats()
        elif list_type == ObjTypes.KLEE_FILE:
            self.data.list_klee_files()
        elif list_type == ObjTypes.KLEE:
            self.data.list_klee()
        elif list_type == ObjTypes.ALL:
            self.data.list_metrics()
            self.data.list_graphs()
            self.data.list_klee()
        else:
            self.logger.v_msg(f"Type {list_type} not recognized")

    def do_metrics(self, flags: Options, name: str) -> None:
        """
        Compute all of the complexity matrics for a Graph object.
        Usage:
        metrics <name>
        metrics *
        """
        # pylint: disable=R1702
        # pylint: disable=R0912
        graphs = [self.data.graphs[name] for name in self.get_metrics_list(name)]
        if self.multi_threaded:
            start_time = time.time()
            self.do_metrics_multithreaded(graphs)
            elapsed = time.time() - start_time
            print(f"TIME ELAPSED: {elapsed}")
        else:
            for graph in graphs:
                self.logger.v_msg(f"Computing metrics for {graph.name}")
                results = []
                if self.rich:
                    table = Table(title=f"Metrics for {graph.name}")
                    table.add_column("Metric", style="cyan")
                    table.add_column("Result", style="magenta", no_wrap=False)
                    table.add_column("Time Elapsed", style="green")
                for metric_generator in self.controller.metrics_generators:
                    # Lines of Code is currently only supported in Python.
                    if metric_generator.name() == "Lines of Code" and \
                       graph.metadata.language is not KnownExtensions.Python:
                        continue
                    start_time = time.time()

                    try:
                        with Timeout(6000, "Took too long!"):
                            result = metric_generator.evaluate(graph)
                            runtime = time.time() - start_time
                        if result is not None:
                            results.append((metric_generator.name(), result))
                            time_out = f"{runtime:.5f} seconds"
                            if metric_generator.name() == "Path Complexity":
                                result_ = cast(tuple[Union[float, str], Union[float, str]],
                                               result)
                                path_out = f"(APC: {result_[0]}, Path Complexity: {result_[1]})"

                                if self.rich:
                                    table.add_row(metric_generator.name(), path_out, time_out)
                                else:
                                    self.logger.v_msg(f"Got {path_out}, {time_out}")
                            else:
                                if self.rich:
                                    table.add_row(metric_generator.name(), str(result), time_out)
                                else:
                                    self.logger.v_msg(f" Got {result}, took {runtime:.3e} seconds")
                        else:
                            self.logger.v_msg("Got None")
                    except TimeoutError:
                        self.logger.e_msg("Timeout!")
                    except IndexError as err:
                        self.logger.e_msg("Index Error")
                        self.logger.e_msg(str(err))
                    except numpy.linalg.LinAlgError as err:
                        self.logger.e_msg("Lin Alg Error")
                        self.logger.e_msg(str(err))
                if self.rich:
                    console = Console()
                    console.print(table)
                if graph.name is not None:
                    self.data.metrics[graph.name] = results

    def do_metrics_multithreaded(self, cfgs: list[ControlFlowGraph]) -> None:
        """Compute all of the metrics for some set of graphs using parallelization."""
        pool_size = 8
        pool = Pool(pool_size)
        manager = Manager()
        graphQueue = manager.Queue()
        lock = manager.Lock()
        v_num = self.data.v_num
        methodList = []
        methods = read_csv(f"experiments/Jmol/metricsFlagsDefects_jmol{self.data.v_num}.csv")
        with open ('experiments/Jmol/metrics_2CSVMethodNames.csv', 'w', newline = '') as methodCSVNameFile:
            methodCSVNameWriter = csv.writer(methodCSVNameFile)
            for method in methods.Method:
                method = self.method_cleaner(method, False)
                methodList.append(method)
                methodCSVNameWriter.writerow([method])
        cfgs = sorted(cfgs, key=lambda cfg: len(cfg.graph.vertices()), reverse=True)
        results: defaultdict[str, list[tuple[str, MetricRes]]] = defaultdict(list)
        shared_dict: dict[tuple[str, str], Union[int, PathComplexityRes]] = manager.dict()
        async_results = []
        # Queue up all of the cfgs / metrics to execute
        for metrics_generator in self.controller.metrics_generators[::-1]:
            for cfg in cfgs:
                # IMPORTANT! 
                if cfg.name in methodList:
                    graphQueue.put((cfg, metrics_generator.name()))
        generator_dict = {generator.name(): generator for generator in self.controller.metrics_generators}
    
        func_to_execute = partial(
            multiprocess_metrics,
            generator_dict,
            shared_dict,
            graphQueue,
            lock)
        args = list(range(pool_size))
        
        res = pool.map(func_to_execute, args, chunksize=1)
        

        # while not res.ready():
        #     print(f"=== Queue Size: {graphQueue.qsize()} ===")
        #     time.sleep(3)
            
        # async_res = pool.map_async(partial(multiprocess_metrics, metrics_generator, shared_dict), graphQueue)
        # async_results.append(async_res)
        # list(map(lambda x: x.wait(), async_results))
        for (name, metric_generator), res in shared_dict.items():
            results[name].append((metric_generator, res))
        # self.data.metrics is a dictionary where the key is a method and the value is a list of lists where the entries
        # are npath, cyclomatic, path complexity, and APC
        #print(f"results:{results}")
        self.data.metrics.update(results)

    def get_metrics_list(self, name: str) -> list[str]:
        """Get the list of metric names from command argument."""
        if name == "*":
            return list(self.data.graphs.keys())

        if name in self.data.graphs:
            return [name]

        try:
            self.logger.d_msg(f"Trying to compile {name} to regexp")
            pattern = re.compile(name)
            args_list = []
            for graph_name in self.data.graphs:
                if pattern.match(graph_name):
                    args_list.append(graph_name)

            return args_list
        except re.error:
            self.logger.v_msg(f"Error, Graph {name} not found.")
            return []
    
    def method_cleaner(self, method: str, printStatus: bool):
        """Making the method names from the CSV file match the graph object name"""
        strMethod = str(method)
        if printStatus:
            print(f"Uncleaned Method: {strMethod}")
        strMethod = strMethod.replace(" ",":")
        indexOfParen = strMethod.index("(")
        method = strMethod[0:indexOfParen]
        if "<init>" in method:
            endingIndex = method.find("<init>")-1
            if ".jmol." in method:
                if ".applet." in method:
                    if printStatus:
                        print("yahhurd")
                    startingIndex = method.find(".applet.")+8
                else:
                    startingIndex = method.find("jmol.")+5 
            elif "freeware." in method:
                startingIndex = 9
            else:
                startingIndex = 12
            constructorName = method[startingIndex:endingIndex]
            if printStatus:
                print(f"Constructor Name: {constructorName}")
            method = method.replace("<init>",constructorName) 
        if printStatus:
            print(f"Cleaned Method: {method}")
        return method

    def do_vector(self, flags: Options) -> None:
        """creates a feature vector for each existing graph, and saves that vector to the file tests/textFiles/test.txt"""
        methods = read_csv(f"experiments/Jmol/metricsFlagsDefects_jmol{self.data.v_num}.csv")
        # metricDict is a dictionary that stores 
        metricDict = {}
        for method in methods.Method:
            method = self.method_cleaner(method, False)
            # self.data have metrics, graphs, klee_stats, klee_formatted_files, bc_file, logger attributes 
            # self.data.metrics is a dictionary where the key is a method and the value is a list of lists where the entries
            # are npath, cyclomatic, path complexity, and APC
            if method not in self.data.metrics.keys():
                metricDict[method] = [-1,-1,-1,-1, -1, "csv method does not match Metrinome object 1"]
                continue
            metric = self.data.metrics[method]
            metric = sorted(metric, key=lambda val: val[0], reverse=True)
            # metric becomes a list of strings where the first element is APC and the second element is PC
            metric = metric[0][1]
            apclist = str(metric[0]).split("*")
            pc = metric[1]
            if len(apclist) == 1: #constant or linear
                if apclist[0] == "n": #linear
                    for entry in pc.split():
                        count = 0
                        for char in entry:
                            if char == "*":
                                count += 1
                        if count == 1: #found the linear term in the PC
                            apclist = [1,0, 0, 0, float(entry.split("*")[0])]
                else: #constant
                    try:
                        apclist = [0, 0, 0, float(apclist[0]), 0]
                    except: # Took too long to run
                        apclist = [-1, -1, -1, -1, -1, "took too long to run"]
            elif len(apclist) == 3: #exponential or polynomial
                pcSplit = pc.replace(" ", "*").split("*")
                for i in range(len(pcSplit) - 2):
                    if pcSplit[i:i+3] == apclist:
                        coeff = pcSplit[i - 1]
                if apclist[0] == "n": #polynomial
                    power = float(apclist[2])
                    apclist = [2, 0, 0, coeff, power]
                else: #exponential
                    base = float(apclist[0])
                    apclist = [3, coeff, base, 0, 0]
            else: #something has gone wrong
                self.logger.e_msg(apclist := "Split APC is not of an expected length")
            metricDict[method] = apclist

           
        newFile = open(f"experiments/Jmol/metrics_{self.data.v_num}.csv", 'w', newline = '')
        with newFile: 
            with open(f"experiments/Jmol/metricsFlagsDefects_jmol{self.data.v_num}.csv") as csv_file:
                newCsvData = []
                csv_reader = csv.reader(csv_file, delimiter=',')
                write = csv.writer(newFile)
                firstLine = True
                # iterates the csv row by row
                for row in csv_reader:
                    if firstLine:
                        featureVectorLabel = ["APC type", "APC exp coeff", "APX exp base", "APC poly coeff", "APC poly power"]
                        newCsvData += row+featureVectorLabel
                        write.writerow(newCsvData)
                        firstLine = False
                    else:
                        # key is the method name given by the CSV (might have to change depending on project and CSV)
                        key = row[2]
                        key = self.method_cleaner(key, True)
                        if key in self.data.metrics.keys():
                            featureVector = metricDict[key]
                        else:
                            featureVector = [-1, -1, -1, -1, -1, "csv method does not match Metrinome object 2"]
                        newRow = row + featureVector 
                        write.writerow(newRow)

    def log_name(self, name: str) -> bool:
        """Log all objects of a given name."""
        found = False
        if name in self.data.graphs:
            self.logger.i_msg("GRAPH")
            self.logger.v_msg(str(self.data.graphs[name]))
            found = True
        if name in self.data.metrics:
            self.logger.i_msg("METRIC")
            self.logger.v_msg(str(self.data.metrics[name]))
            found = True
        if name in self.data.bc_files:
            self.logger.i_msg("BC FILES")
            self.logger.v_msg(str(self.data.bc_files[name]))
            found = True
        if name in self.data.klee_formatted_files:
            self.logger.i_msg("KLEE FILES")
            self.logger.v_msg(self.data.klee_formatted_files[name])
            found = True
        if name in self.data.klee_stats:
            self.logger.i_msg("KLEE STATS")
            self.logger.v_msg(str(self.data.klee_stats[name]))
            found = True
        if not found:
            self.logger.v_msg(f"Object {name} not found.")
        return found

    def do_show_klee(self, flags: Options, obj_type: ObjTypes, names: list[str]) -> bool:
        """Display the KLEE objects the REPL knows about."""
        if obj_type == ObjTypes.KLEE_BC:
            self.data.show_klee_bc(names)
        elif obj_type == ObjTypes.KLEE_FILE:
            self.data.show_klee_files(names)
        elif obj_type == ObjTypes.KLEE_STATS:
            self.data.show_klee_stats(names)
        elif obj_type == ObjTypes.KLEE:
            self.data.show_klee(names)
        else:
            return False

        return True

    def do_show(self, flags: Options, obj_typename: str, arg_name: str) -> None:
        """
        Show an object of some type (either metric, graph, or KLEE type).

        Usage
        show <metric/graph/KLEE type> <name>
        show <metric/graph/KLEE type> *
        """
        names = [arg_name]
        if (obj_type := ObjTypes.get_type(obj_typename)) is None:
            self.logger.e_msg("Unrecognized type.")
            return

        if self.do_show_klee(flags, obj_type, names):
            return

        if obj_type == ObjTypes.METRIC:
            self.data.show_metric(arg_name, names)
        elif obj_type == ObjTypes.GRAPH:
            self.data.show_graphs(arg_name, names)
        elif obj_type == ObjTypes.ALL:
            if arg_name == "*":
                names = list(self.data.metrics.keys()) + list(self.data.graphs.keys()) + \
                    list(self.data.bc_files.keys()) + \
                    list(self.data.klee_formatted_files.keys()) + \
                    list(self.data.klee_stats.keys())
                names = list(set(names))

            for name in names:
                self.log_name(name)
        else:
            self.logger.v_msg(f"Type {obj_type} not recognized.")

    def do_klee_to_bc(self, flags: Options, name: str) -> None:
        """Given a C file in the correct format, generate a new .bc file from the given C file."""
        if name == '*':
            args_list = list(self.data.klee_formatted_files.keys())

        elif name not in self.data.klee_formatted_files:
            self.logger.v_msg(f"Could not find {name}.")
            return

        else:
            args_list = [name]

        for f_name in args_list:
            with tempfile.NamedTemporaryFile(delete=True, suffix=".c") as file:
                self.logger.d_msg(f"Created temporary file {file.name}")
                self.logger.d_msg(f"Going to write {self.data.klee_formatted_files[f_name]}")
                file.write(self.data.klee_formatted_files[f_name].encode())

                file.seek(0)
                self.logger.d_msg("FILE CONTENTS")
                self.logger.d_msg(file.read().decode())

                cmd = f"clang-6.0 -I /app/klee/include -emit-llvm -c -g\
                        -O0 -Xclang -disable-O0-optnone  -o /dev/stdout {file.name}"
                res = subprocess.run(cmd, shell=True, capture_output=True, check=True)
                self.data.bc_files[f_name] = res.stdout
                self.logger.v_msg(f"Created {Colors.MAGENTA.value}{f_name}{Colors.ENDC.value}")

    def do_to_klee_format(self, flags: Options, file_path: str) -> None:
        """
        Create a klee-compatible file.

        Given a C file, create a new modified C file that is in the
        correct format to be converted to a bc file.
        """
        self.logger.d_msg(f"Recursive Mode is {flags.recursive_mode}")
        files = self.get_files(file_path, flags.recursive_mode, [".c"])
        if len(files) == 0:
            self.logger.v_msg(f"Could not find any files for {Colors.MAGENTA.value}{file_path}{Colors.MAGENTA.value}")
            return

        self.logger.d_msg(f"Got files {files}")
        for file in files:
            if (klee_formatted_files := self._klee_utils.show_func_defs(file)) is None:
                return
            self.data.klee_formatted_files = {**self.data.klee_formatted_files,
                                              **klee_formatted_files}
            log_str = f"Created {Colors.MAGENTA.value}{' '.join(list(klee_formatted_files.keys()))}{Colors.ENDC.value}"
            self.logger.v_msg(log_str)

    def klee_output_indices(self, klee_output: str) -> tuple[int, int, int]:
        """Get the indicies of statistics we care about in the Klee output string."""
        strs_to_match = ["generated tests = ", "completed paths = ", "total instructions = "]

        generated_tests_index    = klee_output.index(strs_to_match[0]) + len(strs_to_match[0])
        completed_paths_index    = klee_output.index(strs_to_match[1]) + len(strs_to_match[1])
        total_instructions_index = klee_output.index(strs_to_match[2]) + len(strs_to_match[2])

        return generated_tests_index, completed_paths_index, total_instructions_index

    def update_klee_stats(self, klee_output: str, name: str, delta_t: float) -> None:
        """Parse and store the results of running klee on some .bc file."""
        timed_out = "HaltTimer invoked" in klee_output

        indices = self.klee_output_indices(klee_output)
        generated_tests_index    = indices[0]
        completed_paths_index    = indices[1]
        total_instructions_index = indices[2]

        number_regex = re.compile("[0-9]+")

        tests_match = number_regex.match(klee_output[generated_tests_index:])
        paths_match = number_regex.match(klee_output[completed_paths_index:])
        insts_match = number_regex.match(klee_output[total_instructions_index:])

        if tests_match is not None:
            tests = int(tests_match.group())
        if paths_match is not None:
            paths = int(paths_match.group())
        if insts_match is not None:
            insts = int(insts_match.group())

        self.data.klee_stats[name] = self.data.klee_stat(tests=tests, paths=paths,
                                                         instructions=insts, delta_t=delta_t,
                                                         timeout=timed_out)
        self.logger.i_msg("Updated!")

    def do_klee(self, flags: Options, name: str, *extra_args: str) -> None:
        """
        Execute the klee command on a .bc file.

        This will generate all of the tests automatically and store the resulting metadata
        (e.g. number of tests generated).

        Usage:
        klee <file>
        """
        if name in self.data.bc_files or name == "*":
            self._klee_known_files(flags, name, *extra_args)
        else:
            if (result := self.verify_file_type(name, "bc")) is None:
                return

            files = self.get_files(result, False, [str(KnownExtensions.BC)])
            if len(files) == 0:
                self.logger.e_msg(f"Could not find any files matching {result}")
                return

            self.logger.d_msg(f"Obtained {files}")

            for _ in files:
                cmd = f"/app/build/bin/klee {result}"
                self.logger.d_msg(cmd)
                start_time = time.time()
                res = subprocess.run(cmd, shell=True, capture_output=True, check=True)
                delta_t = time.time() - start_time
                output = res.stderr
                self.logger.d_msg("OUTPUT:")
                self.logger.d_msg(output.decode())
                self.update_klee_stats(output.decode(), name, delta_t)

    def _klee_known_files(self, flags: Options, name: str, *extra_args: str) -> None:
        """Run klee on known files."""
        if name == "*":
            keys = list(self.data.bc_files.keys())
        else:
            keys = [name]

        for key in keys:
            with tempfile.NamedTemporaryFile(delete=True, suffix=".bc") as file:
                self.logger.d_msg(f"Created temporary file {file.name}")
                self.logger.d_msg("Writing")
                file.write(self.data.bc_files[key])
                file.seek(0)

                cmd = "/app/build/bin/klee --max-time=30s " + \
                      "--dump-states-on-halt=false " + \
                      f"{' '.join(extra_args)} {file.name}"
                self.logger.d_msg(f"Going to execute {cmd}")
                start_time = time.time()

                try:
                    with Timeout(60, "Klee command took too long"):
                        res = subprocess.run(cmd, shell=True, capture_output=True, check=True)

                    delta_t = time.time() - start_time
                    output = res.stderr
                    self.logger.d_msg(output.decode())
                    self.logger.d_msg(f"Runtime: {delta_t} seconds")
                    self.logger.d_msg("Updating Klee Stats")
                    self.update_klee_stats(output.decode(), key, delta_t)
                except subprocess.CalledProcessError as error:
                    self.logger.e_msg("Could not run klee")
                    self.logger.d_msg(error.stderr)
                    return
                except TimeoutError as exception:
                    self.logger.e_msg(str(exception))

    def do_quit(self, flags: Options) -> None:
        """Quit the path complexity repl."""
        readline.write_history_file()
        raise SystemExit

    def do_export(self, flags: Options, export_typename: str, name: str) -> None:
        """
        Save an object (type Graph, Metrics, Stats, KLEE type) to an output file.

        Usage:
        save <type> <name>
        """
        subprocess.check_call(["mkdir", "-p", "exports"])
        export_type = ObjTypes.get_type(export_typename)
        if export_type is None:
            self.logger.e_msg("Unrecognized type.")
            return

        new_name = name + "_export"

        if export_type == ObjTypes.GRAPH:
            self.data.export_graph(name, new_name)
        elif export_type == ObjTypes.METRIC:
            self.data.export_metrics(name, new_name)
        elif export_type == ObjTypes.KLEE_BC:
            self.data.export_bc(name, new_name)
        elif export_type == ObjTypes.KLEE_FILE:
            self.data.export_klee_file(name, new_name)
        elif export_type == ObjTypes.KLEE_STATS:
            self.data.export_klee_stats(name, new_name)
        elif export_type == ObjTypes.KLEE:
            self.data.export_bc(name, new_name)
            self.data.export_klee_file(name, new_name)
        else:
            self.logger.e_msg(f"{str(export_type).capitalize()} {name} not found.")

    def do_cd(self, flags: Options, new_path: str) -> None:
        """Change the current working directory."""
        if new_path[0] == "/" and not os.path.isdir(new_path):
            self.logger.e_msg("Not a valid directory.")
            return

        if new_path[0] != "/" and not os.path.isdir(os.path.join(self.curr_path, new_path)):
            self.logger.e_msg("Not a valid directory.")
            return

        self.curr_path = os.path.abspath(os.path.join(self.curr_path, new_path))

    def do_ls(self, flags: Options) -> None:
        """List the files in the current directory."""
        self.logger.v_msg(" ".join(os.listdir(self.curr_path)))

    def do_mkdir(self, flags: Options, dirname: str) -> None:
        """Make a new directory."""
        subprocess.check_call(["mkdir", "-p", dirname])

    def do_mv(self, flags: Options, name_one: str, name_two: str) -> None:
        """Move a file from one directory to another."""
        subprocess.check_call(["mv", name_one, name_two])

    def do_rm(self, flags: Options, *names: str) -> None:
        """Remove files permanently."""
        for name in names:
            if flags.recursive_mode:
                subprocess.check_call(["rm", "-r", name])
            else:
                subprocess.check_call(["rm", name])

    def do_pwd(self, flags: Options) -> None:
        """Print out the current working directory."""
        self.logger.v_msg(self.curr_path)

    def do_delete(self, flags: Options, obj_type: str, name: str) -> None:
        """
        Delete an object (type Graph, Metrics, States, or KLEE type) from memory.

        Usage:
        delete <type> <name>
        """
        self.logger.d_msg(obj_type)
        known_types_dict: dict[str, AnyDict] = {
            ObjTypes.GRAPH.value: self.data.graphs,
            ObjTypes.METRIC.value: self.data.metrics,
            ObjTypes.KLEE_BC.value: self.data.bc_files,
            ObjTypes.KLEE_STATS.value: self.data.klee_stats,
            ObjTypes.KLEE_FILE.value: self.data.klee_formatted_files,
        }
        for known_obj_type in known_types_dict:
            if obj_type == known_obj_type:
                try:
                    known_types_dict[known_obj_type].pop(name)
                except KeyError:
                    self.logger.v_msg(f"{known_obj_type.capitalize()} {name} not found.")
                return

        if obj_type == ObjTypes.KLEE.value:
            found = False
            dictionary_list: list[AnyDict] = [self.data.klee_stats,
                                              self.data.klee_formatted_files,
                                              self.data.bc_files]
            for dictionary in dictionary_list:
                try:
                    del dictionary[name]
                    found = True
                except KeyError:
                    pass
            if not found:
                self.logger.v_msg(f"No {name} found of any KLEE type.")
        elif obj_type == ObjTypes.ALL.value:
            found = False
            dictionary_list = [self.data.graphs, self.data.metrics,
                               self.data.klee_stats, self.data.klee_formatted_files,
                               self.data.bc_files]
            for dictionary in dictionary_list:
                try:
                    del dictionary[name]
                    found = True
                except KeyError:
                    pass
            if not found:
                self.logger.v_msg(f"No {name} found of any type.")
        else:
            self.logger.v_msg(f"Type {type} not recognized.")