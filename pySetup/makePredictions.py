import json
import os
import os.path as path
import sys
import csv
import time
import joblib
import numpy as np
import logging
import xgboost

from scipy.sparse import csr_matrix, vstack

from sendMessages import printParent
from sendMessages import messageParent
from sendMessages import obviousPrint

logging.basicConfig()

fileNames = json.loads(sys.argv[4])
classifierName = sys.argv[5]
argv = json.loads(sys.argv[3])
problemType = sys.argv[6]
trainingScore = sys.argv[7]
copyValidationData = sys.argv[8]

if argv['validationRound']:
    X_file_name = argv['dataFile']

else:
    if( classifierName[0:4] == 'clnn' ):
        nn = True
        X_file_name = fileNames['X_test_nn']
    else:
        nn = False
        X_file_name = fileNames['X_test']

id_file_name = fileNames['id_test']


XTest = []
testIDColumn = []

# load up the prediction data set, without the header row
try:
    def load_sparse_csr(filename):
        loader = np.load(filename)
        return csr_matrix(( loader['data'], loader['indices'], loader['indptr']), shape=loader['shape']) 
    
    XTest = load_sparse_csr(X_file_name)
except:
    with open(X_file_name, 'rU') as x_file:
        inputRows = csv.reader(x_file)
        headerRow = False
        for row in inputRows:
            if(headerRow):
                XTest.append(row)
            else:
                headerRow = True

if argv['validationRound']:
    # in the validation file, we have combined the validationData and the test data
    # split out to only have the test data
    testLength = fileNames['testingDataLength']
    combinedValidationLength = XTest.shape[0]
    testIndices = range( combinedValidationLength - testLength, combinedValidationLength)

    XTest = XTest[ testIndices , : ]

# should be pretty safe to convert the testIDColumn to a list, since it is always going to be a single value per row
# to get a single vector (in this case, our ID column) to be saved as a sparse matrix, we have to do some vaguely hacky stuff
# the following line converts it to a normal python list
testIDColumn = load_sparse_csr( id_file_name ).todense().tolist()[0]


try:
    idHeader = fileNames['idHeader']
    outputHeader = fileNames['outputHeader']
except:
    # read in the y_file simply to get the pretty header name for the output column
    with open(y_file_name, 'rU') as y_file:
        inputRows = csv.reader(y_file)
        outputHeader = False
        for row in inputRows:
            if outputHeader == False:
                outputHeader = row[0]
            else:
                pass

if argv['validationRound']:
    classifierFile = path.join( argv['bestClassifiersFolder'], 'ensemblingAlgos', 'best' + classifierName, 'best' + classifierName + '.pkl')
else:
    classifierFile = path.join( argv['bestClassifiersFolder'], 'best' + classifierName, 'best' + classifierName + '.pkl')

# load up the previously trained (and tuned!) classifier
classifier = joblib.load( classifierFile )

try:
    classifier.set_params(n_jobs=-1)
except:
    pass


# get predictions for each item in the prediction data set
if problemType == 'category':
    try:
        testDataPredictions = classifier.predict_proba(XTest)
    except:
        # perceptron does not support predict_proba
        # and MultinomialNB does not do probability predictions all that well
        testDataPredictions = classifier.predict(XTest)

# else will handle both regression and multi-category predictions at the moment. 
else:
    testDataPredictions = classifier.predict(XTest)


if not argv['validationRound']:
    validationFile = fileNames['X_trainvalidationData']
    validationData = load_sparse_csr(validationFile)
    validationIdFile = fileNames['id_trainvalidationData']
    validationIDs = load_sparse_csr( validationIdFile ).todense().tolist()[0]

    if nn:
        validationYFile = fileNames['y_train_nnvalidationData']
    else:
        validationYFile = fileNames['y_trainvalidationData']
    validationY = load_sparse_csr(validationYFile).todense().tolist()[0]


    if problemType == 'category':
        try:
            validationPredictions = classifier.predict_proba(validationData)
        except:
            validationPredictions = classifier.predict(validationData)
            
    else:
        # else will handle both regression and multi-category predictions for now
        validationPredictions = classifier.predict(validationData)

    validationScore = classifier.score(validationData,validationY)

    printParent('\n')
    printParent('***************')
    printParent(classifierName + "'s score on the validation set is:")
    printParent(validationScore)
    printParent('***************')
else:
    # we still need something to write to the file. unfortunately, for now, that's just going to be another copy of the trainingScore, which we are now writing twice to the first row of the file
    validationScore = trainingScore

# write our predictions on the test data to a file
if argv['validationRound']:
    predictionsPath = path.join( argv['predictionsFolder'], 'ensembledPredictions' )

else:
    predictionsPath = argv['predictionsFolder']


# using the outputFileName here so that if people have different input files (different feature engineering), that will show up in our file names.
predictionsFileName = argv['outputFileName'] + classifierName + str(time.time()) + '.csv'

# create the directory if it doesn't exist already
if not os.path.exists(predictionsPath):
    os.makedirs(predictionsPath)

with open( path.join(predictionsPath, predictionsFileName) , 'w+') as predictionsFile:
    csvwriter = csv.writer(predictionsFile)

    # we are going to have to modify this when we allow it to make categorical predictions too. 
    # TODO: write the scores here!
    csvwriter.writerow([validationScore, trainingScore])
    csvwriter.writerow([idHeader,outputHeader])
    for idx, prediction in enumerate(testDataPredictions):
        rowID = testIDColumn[idx]

        try:
            len(prediction)
            csvwriter.writerow([int(rowID),prediction[1]])
        except:
            csvwriter.writerow([int(rowID),prediction])

if not argv['validationRound']:

    # write our validation predictions to a file too
    validationPath = path.join( predictionsPath, 'validation')
    validationFileName = argv['outputFileName'] + classifierName + str(time.time()) +'.csv'

    # to keep things super consistent, we will combine our test and validation data, so there's no risk of order getting mixed up in ensembler
    totalPredictions = np.concatenate( (validationPredictions, testDataPredictions), axis=0 )
    validationAndTestIDs = np.concatenate( (validationIDs, testIDColumn), axis=0 )

    with open( path.join(validationPath, validationFileName) , 'w+') as validationFile:
        csvwriter = csv.writer(validationFile)

        # at the top of each validation file, write the score for that classifier on the validation set
        csvwriter.writerow([validationScore, trainingScore])

        # we are going to have to modify this when we allow it to make categorical predictions too. 
        csvwriter.writerow([idHeader,outputHeader])
        for idx, prediction in enumerate(totalPredictions):
            rowID = validationAndTestIDs[idx]
            try:
                len(prediction)
                csvwriter.writerow([int(rowID),prediction[1]])
            except:
                csvwriter.writerow([int(rowID),prediction])

    # continued callout to the person originally responsible for this function:
    # http://stackoverflow.com/questions/8955448/save-load-scipy-sparse-csr-matrix-in-portable-data-format
    def save_sparse_csr(filename,array):
        np.savez(filename,data=array.data ,indices=array.indices, indptr=array.indptr, shape=array.shape )

    if copyValidationData and nn == False:
        allValidationDataFile = path.join( validationPath, 'validationData.npz')
        allValidationIDsFile = path.join( validationPath, 'validationIDs.npz')
        allValidationYsFile = path.join( validationPath, 'validationYs.npz')

        # to make sure we keep everything consistent, we write the combined validation data and test data to a file
        allValidationData = vstack( [validationData, XTest] )
        save_sparse_csr(allValidationDataFile, allValidationData)

        # we already loaded in this data, but then immediately converted it to a dense list. 
            # so we are going to load it in again, this time as a sparse csr matrix, and then immediately save it as a sparse csr matrix elsewhere
            # we could just as easily copy the original file to a new location, but since we're not coyping anywhere else, this is slightly more consistent stylistically
        validationSparseIDs = load_sparse_csr( validationIdFile )
        save_sparse_csr( allValidationIDsFile, validationSparseIDs )

        validationSparseYs = load_sparse_csr(validationYFile)
        save_sparse_csr( allValidationYsFile, validationSparseYs )

        # with open( path.join(validationPath, 'validationIDsAndY.csv') , 'w+') as validationFile:
        #     csvwriter = csv.writer(validationFile)

        #     # we are going to have to modify this when we allow it to make categorical predictions too. 
        #     csvwriter.writerow([idHeader,outputHeader])
        #     for idx, rowID in enumerate(validationAndTestIDs):
        #         # our test data will not have y values attached, so we will try to find a y value for this ID, but if we can't, we assume it is a test value, and we set the y value to None
        #         try:
        #             yValue = validationY[idx]
        #         except:
        #             yValue = None
        #         try:
        #             len(yValue)
        #             csvwriter.writerow([int(rowID),yValue[1]])
        #         except:
        #             csvwriter.writerow([int(rowID),yValue])



# if the final output is binary, create a separate file at this stage that can be easily uploaded to kaggle by rounding the predicted value to the nearest int
# We will use the actual probability in ensembler, but it's nice at this stage to be able to upload results to kaggle and get some feedback
if argv[ 'binaryOutput'] == 'true':

    # first check to make sure that we have a distinct file name. if not, append the name of the enclosing folder to the fileName
                    
    # add kaggle to the front of the name to make it obvious that this is for kaggle
    # this also keeps the rest of our files consistent for ensembler
    kagglePath = argv['kaggleBinaryOutputFolder']
    kaggleFileName = argv['outputFileName'] + classifierName + str(time.time()) + '.csv'
    with open( path.join(kagglePath, kaggleFileName) , 'w+') as predictionsFile:
        csvwriter = csv.writer(predictionsFile)

        csvwriter.writerow([idHeader,outputHeader])
        for idx, prediction in enumerate(testDataPredictions):

            rowID = testIDColumn[idx]
            # I'm not sure why we're checking if prediction is already a list
                # or why we're taking the second item in that list
            try:
                len(prediction)
                prediction = int( round( prediction[1] ) )
            except:
                prediction = int( round( prediction ) )
                pass
            csvwriter.writerow( [rowID,prediction] )

# if we can, keep metadata on each file (or, in the array with the file names, hold objects that have information such as observed error rate, relative ranking within all the classifiers of that type, type of classifier, training time, etc.)
