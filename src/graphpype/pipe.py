# Submodule: pipelines. Functions dedicated to constructing pipelines: pre-processing, processing, plotting, and end-to-end functionality.
import importlib, warnings, os, time
import subprocess 
# Constants

# Classes

class Pipeline:
    """Piping object."""
    recipe: any
    paths: list
    result: any
    def __init__(self, recipeDir, bids = {}):

        recipe = Recipe()
        recipe.read(recipeDir)
        self.recipe = recipe
        
        # for each dataset directory find the subject folder names
        subjPaths = {}
        if bids:
            for (dataSetName, directory) in bids.items():
                subjPaths[dataSetName] = [ f.path for f in os.scandir(directory) if f.is_dir() and f.path[0:4] == 'sub-' ]
            subjPaths[dataSetName].insert(0, directory)
        self.paths = subjPaths

    def process(pipe, dataSetNames=[], preProcess=True):
        processingStart = time.time()
        datasets = []
        if preProcess:
            for (dataSetName, paths) in pipe.paths.items():
                _preprocess(pipe.recipe, paths[0])
            
            # construct dataset THIS NEEDS TO BE FIXED
            for (dataSetName, paths) in pipe.paths.items():
                # since the data is preprocessed it needs to be in the derivatives folder and paths must be accordingly modified
                
                directory = paths[0] + "derivatives/"
                dataPaths = [ f.path for f in os.scandir(directory) if f.is_dir() and f.path[len(directory):][0:4] == 'sub-' ]
                ds=[]
                for p in dataPaths:
                    dirsP = []
                    for o in pipe.recipe.nodes["preProcess"]:
                        channel = o.channelOut["preProcess"][0]
                        if "stringAdd" in o.arguments:
                            string = p + o.arguments["stringAdd"]
                        else:
                            string = p
                        dirsP.append({"channel": channel, "string": string})
                    ds.append(Datum(*dirsP))

                datasets.append(DataSet(name=dataSetName, dataObjs=ds))
        
        else:
            if dataSetNames:
                [datasets.append(DataSet(name=i, dataObjs=[])) for i in dataSetNames]
            else:
                ### CHECK THIS
                [datasets.append(DataSet(i, [])) for i in pipe.recipe.nodes if "load" in i.channelsIn]
        
        analysisSet = DataSet(dataObjs=datasets)
        # process: check cache
        #           process nodes
        #           cache
        

        if "preProcess" in pipe.recipe.nodes:
            # do the preprocessing that needs to be applied to the whole data set (e.g. loading already preprocessed data)
            ops = [o for o in pipe.recipe.nodes["preProcess"] if "totalAnalysisPreProcessing" in o.internal]
            res =  _process(ops, [analysisSet], pipe.recipe.env["nThreads"])
            if res:
                analysisSet = res[0]
             
        if "postProcess" in pipe.recipe.nodes:
            ops = pipe.recipe.nodes["postProcess"]
            res = _process(ops, analysisSet.data, pipe.recipe.env["nThreads"])
            if res:
                analysisSet.data = res
        
        if "analysis" in pipe.recipe.nodes:
            ops = pipe.recipe.nodes["analysis"]
            res = _process(ops, analysisSet.data, pipe.recipe.env["nThreads"])
            if res:
                analysisSet.data = res 
        
        if "postAnalysis" in pipe.recipe.nodes:
            ops = pipe.recipe.nodes["postAnalysis"]
            res = _process(ops, [analysisSet], pipe.recipe.env["nThreads"])
            if res:
                analysisSet = res[0]

        pipe.result = analysisSet
        processingFinish = time.time()
        print(f"Total processing time: {processingFinish - processingStart} seconds")

    def output(outputDir):
        # output is classed differently to processing because it is likely to change often and the whole processing pipe needn't be run multiple times
        assert outputDir[0] != '/', "Please use relative directories, not absolute."
        
        if not os.path.exists(outputDir):
            os.mkdir(outputDir)
        
        # change to specified output directory
        os.chdir(os.getcwd() + outputDir)
        ops = self.recipe.nodes["output"]
        for c in ops:
            _process(ops, self.result, self.recipe.env["nThreads"]) 

        if outputDir:
            os.chdir(os.getcwd() + '../')

    def plot(self, outputDir):
        
        import matplotlib.pyplot as plt
        
        plotObjs = self.result.analysis["plots"][0]
        fileNames = self.result.analysis["plots"][1]

        for i in range(len(plotObjs)):
            plotObjs[i].savefig(outputDir + fileNames[i])


class Recipe:
    """Pipeline Recipe: a directed line graph of functions/constants that operate on a subset of data for analysis, output, and plotting. The recipe informs the operations that must be sequentially applied to data and subsequent output manipulations. Recipes can be composed by concatentation."""

    name: str
    """Recipe identifier"""

    description: str
    """Summary of the pipeline flow i.e. brief description of what the recipe cooks."""

    nodes: dict 
    """Functions that the analysis will operate with. The entries are: "preProcess", "postProcess", "analysis", "postAnalysis", and "output". Analysis refers to functions that are applied to a specific data set, while postAnalysis refers to functions that are applied to multiple datasets. Plotting, or output functions such as reports and caching go in the "output" layer."""

    env: dict
    """Any enviroment variables including number of threads, randomisation seed, etc."""

    def __init__(self, name: str="", description: str="", nodes: dict={}, env: dict={"seed": 1, "nThreads": 1}):
        """Initialise a (potentially empty) recipe card with a name and descriptor."""
        self.name = name
        self.description = description
        self.nodes = nodes
        self.env = env

    def report(self, data):
        """Generate a report card summarising the recipe"""

            ### DO THIS ###
    def write(self, outputDir):
        """Write the recipe to disk in .json format for use in pipelines"""
        import json
        with open(outputDir, 'w') as f:
            # print())
            # json_obj = {"name": self.name, "description": self.description, "nodes": sum([[j.json for j in self.nodes[i]] for i in self.nodes], []), "env": self.env}
            nNodes = {}
            for i in self.nodes:
                nNodes[i] = [j.json for j in self.nodes[i]]

            json_obj = {"name": self.name, "description": self.description, "nodes": nNodes, "env": self.env}
            json.dump(json_obj, f, ensure_ascii=False, indent=4)
    
    def read(self, inputDir):
        """Read a recipe in .json format from disk and construct recipe object."""
        import json
        with open(inputDir, 'r') as f:
            recipe = json.load(f) 
        
        self.name = recipe["name"]
        
        self.description = recipe["description"]
        
        self.nodes = {}
        for n in recipe["nodes"]:
            ops = [Operator(**i) for i in recipe["nodes"][n]]
            self.nodes[n] = ops
        
        self.env = recipe["env"]

class Datum:
    """An object that completely specifies a particular element of the dataset with potentially multiple imaging modalities."""

    dirs: list
    """List of the directories used for the specimen/subject in the analysis."""
    preData: dict
    """Dictionary storing the preprocessed data from a particular pipeline such as prepfmri e.g. Dict["Connectivity"] = matrix"""
    postData: dict
    """Dictionary storing the processed data from a particular operator e.g. Dict["Connectivity"] = matrix"""
    
    def __init__(self, *directories):
        self.dirs = []
        self.preData = {} 
        self.postData = {} 
        # list the directories
        for d in directories:
            self.dirs.append(d["string"])
        
        # split the directories to find the relevant information
        for d in directories:

            channel = d["channel"]
            if channel == "Gene":
                import numpy as np
                data = np.load(d["string"])
            elif channel == "fMRI" or channel == "fmri" or channel == "FMRI":
                allNiFTi = [ f.path for f in os.scandir(d["string"]) if f.path[-6:] == 'nii.gz' ]
                import nibabel 
                if d["string"][-1] == '/':
                    print("No specific file selected in data subdirectory, choosing the NIFTI .gz found at the 0'th index of a string matched to `desc-preproc_bold.nii.gz`")
                    target = 'desc-preproc_bold.nii.gz'
                    preProcessedString = [s for s in allNiFTi if s[-len(target):] == target][0]
                    data = nibabel.load(preProcessedString).get_fdata()
                else:
                    assert d["string"][-6:] == 'nii.gz', "Please enter a valid NIFTI archive file"
                    data = nibabel.load(d["string"] + '/nifti.gz').get_fdata()
                
                
            elif channel == "Random":
                from numpy.random import rand
                data = rand(5,2,4,10)
            elif channel == "none":
                data = []
            else:
                raise(AssertionError, "The specified data type is either not supported or not in your BIDS directory.")
            
            self.preData[d["channel"]] = data
    def __call__(self, directory):
        return None
        # append to channel directory
    def addChannel(self, channel, data):
        self.preData[channel] = data
        
class DataSet:
    """A composition of data with type `Datum`. Contains dataset level analysis and processing."""
    name: str
    """A name for the dataset (default: "")"""
    data: list
    """The processed data."""
    analysis: dict
    """Group level analysis of processed data."""
    
    def __init__(self, name="", dataObjs=[]):
        self.name = name
        self.data = []
        self.analysis = {}
        for i in dataObjs:
            self.data.append(i)
    def __call__(self, directory, channel, loader):
        return None
        # append to the analysis
        
class Operator:
    """A processing operator that operates on a discrete chunk of data which either is broadcastover/reduces a data set. The result is stored in the DataType object in a channel indexed as a dictionary and specified by this operator. 
    

    Usage: Operator(function, channels, arguments, inter)
        To specify the function:
        function = {"name": name of the function,
                    "package": e.g numpy.random,
                    "version": blank if installed package / directory of user defined function}
        
        channels ={{"dataIndex": {"Layer": ["Channel1", "Channel2", etc]}, {"Layer2": ["Channel0"]}}, 
                    {"resultIndex": {"Layer": ["SingleChannel"]}}}
        
        arguments = {"unnamed" = [], "alpha": 0, "beta": 1}

        inter = {}, {"broadcast": True}
        The default is to apply the operator to the function channel as is but occasionally you might want to broadcast over a list of elements in the channel e.g. doing a spin correction.

    """
    opName: str
    """A local understandable name."""
    description: str
    """A description of what the operator does."""
    name: str
    basePackage: str
    """Give the package name."""
    packageDir: str
    version: str
    """Give the version number for the locally installed package. If the function is self defined then provide the relative directory."""
    arguments: dict
    """The arguments required to run the operator. Unnamed arguments should be assigned to the dictionary entry unnamed."""
    internal: dict
    """A dictionary of internal operating requirements e.g. broadcast, reduce. Broadcast and reduce will always be applied to the first index of the data channels"""
    channelsIn: list
    """The shape of the container of the incoming data. The first entry specifies the layer on which the operator should function"""
    channelOut: list
    """The shape of the container of the returned data."""
    json: list
    def __init__(self, name=str, description=str, function=dict, channels=dict, args=dict, inter={}):

        assert channels["dataIndex"], "You must supply a data channel/s in the form of a dictionary keys for each operator. The operator will broadcast over the supplied channels."
        self.channelsIn = channels["dataIndex"]
        
        assert channels["resultIndex"], "You must supply a layer and data channel  which will be asscociated with the results."
        self.channelOut = channels["resultIndex"]

        assert type(function["name"])==str, "You must supply a function name."
        self.name = function["name"]

        self.opName=name
        self.description=description
        
        if ("local" in function) and (function["local"] == 1):
            self.version = function["local"]
            self.packageDir = "local" # THINK ABOUT THIS, PERHAPS USERS WANT TO SPECIFY WITHIN A FILE TREE
        elif function["local"] == 0:
            self.basePackage = ""
            self.packageDir = ""
            if "." in function["package"]:
                self.basePackage += function["package"][0:function["package"].index(".")]
                self.packageDir += function["package"][(function["package"].index(".") + 1):]
            else:
                self.basePackage = function["package"]

            if "version" in function:
                self.version = function["version"]
            else:
                pkg = importlib.import_module(self.basePackage)
                if pkg:
                    if pkg.__version__:
                        self.version = pkg.__version__
                    elif importlib.metadata(basePkg):
                        self.version = importlib.metadata(basePkg)
                else:
                    warnings.warn("Couldn't find a version for the function being called: setting version to 0.0.0", UserWarning)
                    self.version = "0.0.0"
        
        # grab all the defaults of the particular function that aren't included in arguments
        f = getattr(pkg, self.name)
        if f.__defaults__==None:
            full_args = {}
        else:
            full_args = dict(zip(f.__code__.co_varnames[-len(f.__defaults__):], f.__defaults__))
        
        shared_keys = tuple(full_args.keys() and args.keys())
        
        # change the default arguments to the user specified ones
        for key in shared_keys:
            full_args[key] = args[key]
        
        self.arguments = full_args
        
        self.internal = inter
        self.json = {"function": function, "channels": channels, "args": args, "inter": inter} 
    def __call__(self, data, ret=True):
        """The operator can be used to operate on a datum by specifying the data layers and channels. The data will be stored in a strictly ordered vector which will be passed as a tuple to the function which defines the operator with the order being inherited from the order used to specify the channels. The result is stored in a single channel in a layer specified by the `channelOut` field."""

        if self.packageDir == "":
            pkg = importlib.import_module(self.basePackage)
        else:
            pkg = importlib.import_module(self.basePackage + "." + self.packageDir)
        f = getattr(pkg, self.name)
        
        if type(data) == Datum:
            d = []
            for i in self.channelsIn:
                if i == "preData":
                    for g in self.channelsIn[i]:
                        d.append(data.preData[g])
                elif i == "postData":
                    for g in self.channelsIn[i]:
                        d.append(data.postData[g])
                else:
                    raise NameError("There is no valid layer by that name.")
            
            if self.internal["broadcast"]:
                # always broadcast over the first provided channel
                for i in range(d[0]):
                    v = [d[x][i % len(d[x])] for x in d]
                    res = f(*v, **self.arguments)
            else:
                if self.arguments["unnamed"]:
                    v = self.arguments["unnamed"]
                    res = f(*d, *v, **self.arguments)
                else:    
                    res = f(*d, **self.arguments)
            
            for c in self.channelOut:
                if c == "preData":
                    data.preData[self.channelOut[c]] = res
                if c == "postData":
                    if inter["split"]:
                        for i in range(len(res)):
                            data.postData[self.channelOut[c] + str(i) ] = res[i]
                    else:
                        data.postData[self.channelOut[c]] = res
        
        elif type(data) == str:
            f(data, **self.arguments)
        
        elif type(data) == DataSet: 
            for i in self.channelsIn:
                d = []
                if i == "preProcess":
                    if "totalAnalysisPreProcessing" in self.internal and self.internal["totalAnalysisPreProcessing"]:
                        d = data.data
                    else:
                        d = [data]
  
                elif i == "postProcess":
                    d = [[x.postData[g] for g in self.channelsIn[i]] for x in data.data]

                elif i == "analysis":
                    ### TO DO: ensure this works for a single data set as well as a list of datasets (recommended)
                    if "postAnalysis" in self.channelOut:
                        if len(self.channelsIn[i]) == 1:
                            d = [j.analysis[g] for g in self.channelsIn[i] for j in data.data]
                        else:
                            d = [[j.analysis[g] for g in self.channelsIn[i]] for j in data.data]
                    else:
                        d = [data.analysis[g] for g in self.channelsIn[i]]
                elif i == "postAnalysis":
                    if self.internal["totalDataSet"]:
                        d = [data]
                    else:
                        d = data.data
                else:
                    raise NameError("There is no valid layer by that name.")
            if "broadcast" in self.internal:
                # always broadcast over the first provided channel
                res = []
                for i in range(len(d[0])):
                    v = [x[i % len(x)] for x in d]
                    res.append(f(*v, **self.arguments))
            else:
                if "unnamed" in self.arguments:
                    v = self.arguments["unnamed"]
                    named = self.arguments.copy()
                    named.pop("unnamed", 'None')
                    if d:
                        res = f(*d, *v, **named)
                    else:
                        res = f(*v, **named)
                else:
                    res = f(*d, **self.arguments)
            
            for c in self.channelOut:
                if "split" in self.internal and self.internal["split"] == True:
                    if "broadcast" in self.internal:
                        step = len(res[0])
                        for i in range(step):
                            data.analysis[self.channelOut[c][0] + str(i)] = [r[i] for r in res]
                    else:
                        for i in range(len(res)):
                            data.analysis[self.channelOut[c][0] + str(i)] = res[i]
                else:
                    assert len(self.channelOut[c]) <= 1, "Multichannel output not yet supported"
                    
                    if self.channelOut[c] != []: # empty channels should not through errors or write results
                        data.analysis[self.channelOut[c][0]] = res

            if ret:
                return data

# TO DO

# Functions

# # # Piping
def _preprocess(recipe, bidsdir):
    """Apply a preprocessing pipeline to a directory of data in the BIDS standard. Currently only command line based preprocessing pipes are supported. A user defined pipeline can be specified using a series of operators on a list of directories."""
    
    assert "preProcess" in recipe.nodes, "You need to specify the preprocessing operations." 
    
    ops = recipe.nodes["preProcess"]
    for i in ops:
        if i.basePackage == "cmd":
            cmdStr =[k + v for (k, v) in i.arguments.items()][0].split()
            subprocess.run(cmdStr)
        else:
            # the bidsdir includes all names of the subject paths as elements of a vector; the first element of the vector is the root of the data directory
            [f(bidsdir) for f in ops]

def _process(ops, dataset, nthreads: int, pool=None):
    if nthreads > 1:
      #  import multiprocessing
      #  for f in ops:
      #     if f.name != 'plots': ## Change this to env["nonparallel"]
      #          lambdaF = lambda x: f(x)
      #          pool.map(f, dataset)
      #      else:
      #          [f(d) for d in dataset]

        from joblib import Parallel, delayed, cpu_count
        from joblib.externals.loky import set_loky_pickler
        set_loky_pickler('pickle')
        pool = Parallel(n_jobs=-1, prefer='threads', backend='multiprocessing')
        for f in ops:
            if f.name != 'plots': ## Change this to env["nonparallel"]
                dataset = pool(delayed(f)(d, ret=True) for d in dataset)
            else:
                [f(d) for d in dataset]
        return dataset
    else:
        for d in dataset:            
            [f(d, ret=False) for f in ops]


            

