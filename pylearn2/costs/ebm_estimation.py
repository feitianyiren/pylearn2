""" Training costs for unsupervised learning of energy-based models """
import theano.tensor as T
from theano import scan
from pylearn2.costs.cost import Cost
from pylearn2.space import CompositeSpace
from pylearn2.utils import py_integer_types
from collections import OrderedDict
from itertools import izip
from pylearn2.models.rbm import BlockGibbsSampler
import numpy as np

if 0:
    print 'WARNING: using SLOW rng'
    RandomStreams = tensor.shared_randomstreams.RandomStreams
else:
    import theano.sandbox.rng_mrg
    RandomStreams = theano.sandbox.rng_mrg.MRG_RandomStreams

class NCE(Cost):
    """ Noise-Contrastive Estimation

        See "Noise-Contrastive Estimation: A new estimation principle for unnormalized models "
        by Gutmann and Hyvarinen

    """
    def h(self, X, model):
        return - T.nnet.sigmoid(self.G(X, model))


    def G(self, X, model):
        return model.log_prob(X) - self.noise.log_prob(X)

    def expr(self, model, data, noisy_data=None):
        # noisy_data is not considered part of the data.
        #If you don't pass it in, it will be generated internally
        #Passing it in lets you keep it constant while doing
        #a learn search across several theano function calls
        #and stuff like that
        space, source = self.get_data_specs(model)
        space.validate(data)
        X = data
        if X.name is None:
            X_name = 'X'
        else:
            X_name = X.name

        m_data = X.shape[0]
        m_noise = m_data * self.noise_per_clean

        if noisy_data is not None:
            space.validate(noisy_data)
            Y = noisy_data
        else:
            Y = self.noise.random_design_matrix(m_noise)

        #Y = Print('Y',attrs=['min','max'])(Y)

        #hx = self.h(X, model)
        #hy = self.h(Y, model)

        log_hx = -T.nnet.softplus(-self.G(X,model))
        log_one_minus_hy = -T.nnet.softplus(self.G(Y,model))


        #based on equation 3 of the paper
        #ours is the negative of theirs because they maximize it and we minimize it
        rval = -T.mean(log_hx)-T.mean(log_one_minus_hy)

        rval.name = 'NCE('+X_name+')'

        return rval

    def __init__(self, noise, noise_per_clean):
        """
        params
        -------
            noise: a Distribution from which noisy examples are generated
            noise_per_clean: # of noisy examples to generate for each clean example given
        """

        self.noise = noise

        assert isinstance(noise_per_clean, py_integer_types)
        self.noise_per_clean = noise_per_clean

    def get_data_specs(self, model):
        space = model.get_input_space()
        source = model.get_input_source()
        return (space, source)


class SM(Cost):
    """ Score Matching
        See eqn. 4 of "On Autoencoders and Score Matching for Energy Based Models",
        Swersky et al 2011, for details

        Uses the mean over visible units rather than sum over visible units
        so that hyperparameters won't depend as much on the # of visible units
    """
    def expr(self, model, data):
        self.get_data_specs(model)[0].validate(data)
        X = data
        X_name = 'X' if X.name is None else X.name

        score = model.score(X)

        sq = 0.5 * T.sqr(score)

        def f(i, fX, fscore):
            score_i_batch = fscore[:,i]
            dummy = score_i_batch.sum()
            full_grad = T.grad(dummy, fX)
            return full_grad[:,i]

        second_derivs, ignored = scan( f, sequences = T.arange(X.shape[1]), non_sequences = [X, score] )
        second_derivs = second_derivs.T

        assert len(second_derivs.type.broadcastable) == 2

        temp = sq + second_derivs

        rval = T.mean(temp)

        rval.name = 'sm('+X_name+')'

        return rval

    def get_data_specs(self, model):
        return (model.get_input_space(), model.get_input_source())


class SMD(Cost):
    """ Denoising Score Matching
        See eqn. 4.3 of "A Connection Between Score Matching and Denoising Autoencoders"
        by Pascal Vincent for details

        Note that instead of using half the squared norm we use the mean squared error,
        so that hyperparameters don't depend as much on the # of visible units
    """

    def __init__(self, corruptor):
        super(SMD, self).__init__()
        self.corruptor = corruptor

    def expr(self, model, data):
        self.get_data_specs(model)[0].validate(data)
        X = data
        X_name = 'X' if X.name is None else X.name

        corrupted_X = self.corruptor(X)

        if corrupted_X.name is None:
            corrupted_X.name = 'corrupt('+X_name+')'
        #

        model_score = model.score(corrupted_X)
        assert len(model_score.type.broadcastable) == len(X.type.broadcastable)
        parzen_score = T.grad( - T.sum(self.corruptor.corruption_free_energy(corrupted_X,X)), corrupted_X)
        assert len(parzen_score.type.broadcastable) == len(X.type.broadcastable)

        score_diff = model_score - parzen_score
        score_diff.name = 'smd_score_diff('+X_name+')'


        assert len(score_diff.type.broadcastable) == len(X.type.broadcastable)


        #TODO: this could probably be faster as a tensordot, but we don't have tensordot for gpu yet
        sq_score_diff = T.sqr(score_diff)

        #sq_score_diff = Print('sq_score_diff',attrs=['mean'])(sq_score_diff)

        smd = T.mean(sq_score_diff)
        smd.name = 'SMD('+X_name+')'

        return smd

<<<<<<< HEAD
class SML(Cost):
    """ Stochastic Maximum Likelihood

        See "On the convergence of Markovian stochastic algorithms with rapidly 
             decreasing ergodicity rates" 
        by Laurent Younes (1998)
        
        Also known as Persistent Constrastive Divergence (PCD)
        See "Training restricted boltzmann machines using approximations to
             the likelihood gradient" 
        by Tijmen Tieleman  (2008)
    """

    def __init__(self, batch_size, nsteps ):
        """
            The number of particles fits the batch size.

            Parameters
            ---------
            batch_size: int
                batch size of the training algorithm
            nsteps: int
                number of steps made by the block Gibbs sampler
                between each epoch
        """
        super(SML, self).__init__()
        self.nchains = batch_size
        self.nsteps  = nsteps

    def get_gradients(self, model, X, Y=None, **kwargs):
        cost = self._cost(model,X,Y,**kwargs)

        params = list(model.get_params())

        grads = T.grad(cost, params, disconnected_inputs = 'ignore', 
                       consider_constant = [self.sampler.particles])

        gradients = OrderedDict(izip(params, grads))

        updates = OrderedDict()

        sampler_updates = self.sampler.updates()
        updates.update(sampler_updates)
        return gradients, updates

    def _cost(self, model, X, Y = None):
        X_name = 'X' if X.name is None else X.name

        if not hasattr(self,'sampler'):
            self.sampler = BlockGibbsSampler(
                rbm=model, 
                particles=0.5+np.zeros((self.nchains,model.get_input_dim())), 
                rng=model.rng, 
                steps=self.nsteps)

        # compute negative phase updates
        sampler_updates = self.sampler.updates()

        # Compute SML cost
        pos_v = X
        neg_v = self.sampler.particles

        ml_cost = (model.free_energy(pos_v).mean()-
                   model.free_energy(neg_v).mean())

        ml_cost.name = 'SML('+X_name+')'
        
        return ml_cost

    def __call__(self, model, X, Y = None):
        return None

class CDk(Cost):
    """ Contrastive Divergence

        See "Training products of experts by minimizing contrastive divergence" 
        by Geoffrey E. Hinton (2002)
    """

    def __init__(self, nsteps, seed=42):
        """
            Parametes
            ---------
            nsteps: int
                number of Markov chain steps for the negative sample
            seed: int
                seed for the random number generator
        """
 
        super(CDk, self).__init__()
        self.nsteps  = nsteps
        self.rng = RandomStreams(seed)

    def _cost(self, model, X, Y = None):
        X_name = 'X' if X.name is None else X.name

        pos_v = X
        neg_v = X
        
        for k in range(self.nsteps):
            [neg_v, _locals] = model.gibbs_step_for_v(neg_v,self.rng)

        # Compute CD cost
        ml_cost = (model.free_energy(pos_v).mean()-
                   model.free_energy(neg_v).mean())

        ml_cost.name = 'CD('+X_name+')'
        
        return ml_cost, neg_v

    def get_gradients(self, model, X, Y=None, **kwargs):
        cost, neg_v = self._cost(model,X,Y,**kwargs)

        params = list(model.get_params())

        grads = T.grad(cost, params, disconnected_inputs = 'ignore',
                       consider_constant = [neg_v])

        gradients = OrderedDict(izip(params, grads))

        updates = OrderedDict()

        return gradients, updates

    def __call__(self, model, X, Y = None):
        return None
=======
    def get_data_specs(self, model):
        return (model.get_input_space(), model.get_input_source())
>>>>>>> upstream/master
