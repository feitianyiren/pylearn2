import numpy as np
from pylearn2.models.mnd import DiagonalMND
from pylearn2.models.mnd import kl_divergence
from pylearn2.optimization.batch_gradient_descent import BatchGradientDescent
from theano import config
from theano import function
floatX = config.floatX

class Test_DiagonalMND:
    """ Class for testing DiagonalMND """

    def __init__(self):
        dim = 3

        self.dim = dim

        self.p = DiagonalMND( nvis = dim,
                init_beta = 1.,
                init_mu = 0.,
                min_beta = 1e-6,
                max_beta = 1e6)

        self.q = DiagonalMND( nvis = dim,
                init_beta = 1.,
                init_mu = 0.,
                min_beta = 1e-6,
                max_beta = 1e6)

    def test_same_zero(self):
        """ checks that two models with the same parameters
        have zero KL divergence """

        rng = np.random.RandomState([1,2,3])

        dim = self.dim

        num_trials = 3

        for trial in xrange(num_trials):
            mu = rng.randn(dim).astype(floatX)
            beta = rng.uniform(.1,10.,(dim,)).astype(floatX)

            self.p.mu.set_value(mu)
            self.q.mu.set_value(mu)
            self.p.beta.set_value(beta)
            self.q.beta.set_value(beta)

            kl = kl_divergence(self.q,self.p)

            kl = function([],kl)()

            tol = 1e-7
            if kl > tol:
                raise AssertionError("KL divergence between two "
                        "equivalent models should be 0 but is "+
                        str(kl))
            #second check because the above evaluates to False
            #if kl is None, etc.
            assert kl <= tol

    def test_nonnegative_samples(self):
        """ checks that the kl divergence is non-negative
            at sampled parameter values for q and p"""

        rng = np.random.RandomState([1,2,3])

        dim = self.dim

        num_trials = 3

        for trial in xrange(num_trials):
            mu = rng.randn(dim).astype(floatX)
            beta = rng.uniform(.1,10.,(dim,)).astype(floatX)
            self.p.mu.set_value(mu)
            mu = rng.randn(dim).astype(floatX)
            self.q.mu.set_value(mu)
            self.p.beta.set_value(beta)
            beta = rng.uniform(.1,10.,(dim,)).astype(floatX)
            self.q.beta.set_value(beta)

            kl = kl_divergence(self.q,self.p)

            kl = function([],kl)()

            if kl < 0.:
                raise AssertionError("KL divergence should "
                        "be non-negative but is "+
                        str(kl))

    def test_zero_optimal(self):
        """ minimizes the kl divergence between q and p
            using batch gradient descent and checks that
            the result is zero"""

        rng = np.random.RandomState([1,2,3])

        dim = self.dim

        num_trials = 3

        mu = rng.randn(dim).astype(floatX)
        beta = rng.uniform(.1,10.,(dim,)).astype(floatX)
        self.p.mu.set_value(mu)
        mu = rng.randn(dim).astype(floatX)
        self.q.mu.set_value(mu)
        self.p.beta.set_value(beta)
        beta = rng.uniform(.1,10.,(dim,)).astype(floatX)
        self.q.beta.set_value(beta)

        kl = kl_divergence(self.q,self.p)

        p = self.p
        q = self.q

        optimizer = BatchGradientDescent(
                    objective = kl,
                    params = [ p.mu, p.beta, q.mu, q.beta ],
                    param_constrainers = [ p.censor_updates,
                        q.censor_updates ])

        #optimizer.verbose = True

        kl = optimizer.minimize()

        if kl < 0.:
            raise AssertionError("KL divergence should "
                    "be non-negative but is "+
                    str(kl))

        tol = 5.4e-5
        assert kl <= tol
        assert not (kl > tol )

