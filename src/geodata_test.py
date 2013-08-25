'''
Created on 2013-08-24 

Unittest for the PyGeoDat main package geodata.

@author: Andre R. Erler, GPL v3
'''

import unittest
import netCDF4 as nc
import numpy as np

# import modules to be tested
from geodata.misc import isZero, isEqual
from geodata import Variable, Axis

class BaseTest(unittest.TestCase):  
  
  # some test parameters (TestCase does not take any arguments)  
  plot = False # whether or not to display plots 
  stats = False # whether or not to compute stats on data
  
  def setUp(self):
    ''' create Axis and a Variable instance for testing '''
    # some setting that will be saved for comparison
    self.size = (3,3,3) # size of the data array and axes
    te, ye, xe = self.size
    self.atts = dict(name = 'test',units = 'n/a',FillValue=-9999)
    self.data = np.random.random(self.size)   
    # create axis instances
    t = Axis(name='t', units='none', coord=(1,te,te))
    y = Axis(name='y', units='none', coord=(1,ye,ye))
    x = Axis(name='x', units='none', coord=(1,xe,xe))
    self.axes = (t,y,x)
    # create axis and variable instances (make *copies* of data and attributes!)
    self.var = Variable(name=self.atts['name'],units=self.atts['units'],axes=self.axes,
                        data=self.data.copy(),atts=self.atts.copy())
    # check if data is loaded (future subclasses may initialize without loading data by default)
    if not self.var.data: self.var.load(self.data.copy()) # again, use copy!
        
  def tearDown(self):
    ''' clean up '''     
    self.var.unload() # just to do something... free memory
    
  ## basic tests every variable class should pass

  def testLoad(self):
    ''' test data loading and unloading '''
    # get test objects
    var = self.var
    # unload and load test
    var.unload()
    var.load(self.data.copy())
    assert self.size == var.shape
    assert isEqual(self.data, var.data_array)
    
  def testAttributes(self):
    ''' test handling of attributes '''
    # get test objects
    var = self.var; atts = self.atts
    # test getattr
    assert (atts['name'],atts['units']) == (var.name,var.units)
    # test setattr
    var.Comments = 'test'; var.plotComments = 'test' 
    #     print 'Name: %s, Units: %s, Missing Values: %s'%(var.name, var.units, var._FillValue)
    #     print 'Comments: %s, Plot Comments: %s'%(var.Comments,var.plotatts['plotComments'])

  def testIndexing(self):
    ''' test indexing and slicing '''
    # get test objects
    var = self.var
    # indexing (getitem) test
    assert self.data[1,1,1] == var[1,1,1].filled(0)
    assert isEqual(self.data[:,1,1:-1], var[:,1,1:-1].filled(0))
      
  def testArithmetic(self):
    ''' test arithmetic functions '''
    # get test objects
    var = self.var
    # arithmetic test
    var += 2.
    var -= 2.
    var *= 2.
    var /= 2.
    # test results
    #     print (self.data.filled() - var.data_array.filled()).max()
    assert isEqual(self.data, var.data_array.filled(0))
    
  def testAxis(self):
    ''' test stuff related to axes '''
    # get test objects
    var = self.var
    # test contains 
    for ax,n in zip(self.axes,self.size):
      assert ax in var
      assert len(ax) == n
#       if ax in var: print '%s is the %i. axis and has length %i'%(ax.name,var[ax]+1,len(ax))


# import modules to be tested
from geodata.netcdf import VarNC, AxisNC

class NetCDFTest(BaseTest):  
  
  # some test parameters (TestCase does not take any arguments)
  dataset = 'GPCC' # dataset to use (also the folder name)
  RAM = True # base folder for file operations
  plot = False # whether or not to display plots 
  stats = False # whether or not to compute stats on data
  
  def setUp(self):
    if self.RAM: folder = '/media/tmp/'
    else: folder = '/home/DATA/DATA/%s/'%self.dataset # dataset name is also in folder name
    if self.dataset == 'GPCC':
      # load a netcdf dataset, so that we have something to play with
      self.ncdata = nc.Dataset(folder+'gpccavg/gpcc_25_clim_1979-1988.nc',mode='r')
    # need to implement non-coordinate dimensions: maybe just Axis? 
    # and what about mixing Axis and AxisNC?
    te = len(self.ncdata.dimensions['time'])
    time = Axis(name='time', length=te) # twelve month 
    xe = len(self.ncdata.dimensions['lon'])
    lon = AxisNC(self.ncdata.variables['lon'], length=xe)
    ye = len(self.ncdata.dimensions['lat'])
    lat = AxisNC(self.ncdata.variables['lat'], length=ye)
    self.size = (te,ye,xe)
    self.axes = (time,lat,lon)
    # initialize netcdf variable 
    self.ncvar = self.ncdata.variables['rain']
    self.var = VarNC(self.ncvar, axes=self.axes, load=True)    
    # save the original netcdf data
    self.data = self.ncdata.variables['rain'][:].filled(0)
    # construct attributes dictionary from netcdf attributes
    self.atts = { key : self.ncvar.getncattr(key) for key in self.ncvar.ncattrs() }
    self.atts['name'] = self.ncvar._name
    if 'units' not in self.atts: self.atts['units'] = '' 
      
  def tearDown(self):  
    self.var.unload()   
    self.ncdata.close()
  
  ## specific NetCDF test cases

    
    
if __name__ == "__main__":

    # construct dictionary of test classes defined above
    test_classes = dict()
    local_values = locals().copy()
    for key,val in local_values.iteritems():
      if key[-4:] == 'Test':
        test_classes[key[:-4]] = val

    # list of tests to be performed
    tests = ['Base'] 
    tests = ['NetCDF']
    
    # run tests
    for test in tests:
      s = unittest.TestLoader().loadTestsFromTestCase(test_classes[test])
      unittest.TextTestRunner(verbosity=2).run(s)