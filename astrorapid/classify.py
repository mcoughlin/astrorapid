import os
import numpy as np
from collections import OrderedDict
from keras.models import load_model
from pkg_resources import resource_filename
from distutils.spawn import find_executable

from astrorapid.process_light_curves import read_multiple_light_curves
from astrorapid.prepare_arrays import PrepareInputArrays

try:
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    import matplotlib
    import matplotlib.animation as animation

    # Check if latex is installed
    if find_executable('latex'):
        plt.rcParams['text.usetex'] = True
    plt.rcParams['font.serif'] = ['Computer Modern Roman'] + plt.rcParams['font.serif']

except ImportError:
    print("Warning: You will need to install 'matplotlib' if you wish to plot the classifications.")


CLASS_NAMES = ['Pre-explosion', 'SNIa-norm', 'SNIbc', 'SNII', 'SNIa-91bg', 'SNIa-x', 'point-Ia', 'Kilonova', 'SLSN-I',
               'PISN', 'ILOT', 'CART', 'TDE']
CLASS_COLOR = {'Pre-explosion': 'grey', 'SNIa-norm': 'tab:green', 'SNIbc': 'tab:orange', 'SNII': 'tab:blue',
               'SNIa-91bg': 'tab:red', 'SNIa-x': 'tab:purple', 'point-Ia': 'tab:brown', 'Kilonova': '#aaffc3',
               'SLSN-I': 'tab:olive', 'PISN': 'tab:cyan', 'ILOT': '#FF1493', 'CART': 'navy', 'TDE': 'tab:pink'}
PB_COLOR = {'u': 'tab:blue', 'g': 'tab:blue', 'r': 'tab:orange', 'i': 'm', 'z': 'k', 'Y': 'y'}
PB_MARKER = {'g': 'o', 'r': 's'}
PB_ALPHA = {'g': 0.3, 'r': 1.}
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


class Classify(object):
    def __init__(self, light_curves, known_redshift=True, model_filepath='', passbands=('g', 'r'),
                 bcut=False, zcut=None, graph=None, model=None):
        """ Takes a list of photometric information and classifies light curves as a function of time

        Parameters
        ----------
        light_curves : list
            Is a list of tuples. Each tuple contains the light curve information of a transient object in the form
            (mjd, flux, fluxerr, passband, zeropoint, photflag, ra, dec, objid, redshift, mwebv).
            Here, mjd, flux, fluxerr, passband, zeropoint, and photflag are arrays.
            ra, dec, objid, redshift, and mwebv are floats
        known_redshift : bool
            Different model to be used if redshift is not known.
        model_filepath : str
            Optional argument. The model is taken from the pre-trained model ZTF model if not specified.
        passbands : tuple
            Optional argument. A tuple listing each passband. E.g. ('g', 'r').
        bcut : bool
            Cut on galactic latitude.
            Do not set unless you know what you are doing.
        zcut : float or None
            Remove redshifts above this value.
            Do not set unless you know what you are doing.
        graph : tensorflow graph
            Do not set unless you know what you are doing.
            If you are running astrorapid in multiple threads you may need to predefine this
            This would have been created with Tensorflow i.e. graph = tf.get_default_graph()
        model : tensorflow model
            Do not set unless you know what you are doing.
            If you are running astrorapid in multiple threads you may need to predefine this
            This would have been created with keras' load_model function e.g. model = load_model('keras_model.hdf5')

        """
        self.light_curves = light_curves
        self.known_redshift = known_redshift
        self.passbands = passbands
        self.bcut = bcut
        self.zcut = zcut
        self.class_names = CLASS_NAMES

        if self.known_redshift:
            self.contextual_info = (0,)
            filename = 'keras_model_with_redshift.hdf5'
        else:
            self.contextual_info = ()
            filename = 'keras_model_no_redshift.hdf5'

        if model_filepath != '' and os.path.exists(model_filepath):
            self.model_filepath = model_filepath
            print("Invalid keras model. Using default model...")
        else:
            self.model_filepath = os.path.join(SCRIPT_DIR, filename)
            if not os.path.exists(self.model_filepath):
                self.model_filepath = resource_filename(__name__, 'keras_model_with_redshift.hdf5')

        print(self.model_filepath)
        self.graph = graph
        if graph is not None and model is not None:
            self.model = model
        else:
            self.model = load_model(self.model_filepath)

    def process_light_curves(self):
        processed_lightcurves = read_multiple_light_curves(self.light_curves, known_redshift=self.known_redshift,
                                                           training_set_parameters=None)
        prepareinputarrays = PrepareInputArrays(self.passbands, self.contextual_info, self.bcut, self.zcut)
        X, orig_lc, timesX, objids_list, trigger_mjds = prepareinputarrays.prepare_input_arrays(processed_lightcurves)

        return X, orig_lc, timesX, objids_list, trigger_mjds

    def get_predictions(self, return_predictions_at_obstime=False):
        """ Return the classifcation accuracies as a function of time for each class

        Parameters
        ----------
        return_predictions_at_obstime: bool
            Return the predictions at the observation times instead of at the 50 interpolated timesteps.

        Returns
        -------
        y_predict: array
            Classification probability vector at each time step for each object.
            Array of shape (s, n, m) is returned.
            Where s is the number of obejcts that are classified,
            n is the number of times steps, and m is the number of classes.
        time_steps: array
            MJD time steps corresponding to the timesteps of the y_predict array.

        """

        self.X, self.orig_lc, self.timesX, self.objids, self.trigger_mjds = self.process_light_curves()
        nobjects = len(self.objids)

        if nobjects == 0:
            print("No objects to classify. These may have been removed from the chosen selection cuts")
            return None, None

        if self.graph is not None:
            with self.graph.as_default():
                self.y_predict = self.model.predict(self.X)
        else:
            self.y_predict = self.model.predict(self.X)

        argmax = self.timesX.argmax(axis=1) + 1

        if return_predictions_at_obstime:
            (s, n, m) = self.y_predict.shape  # (s, n, m) = (num light curves, num timesteps, num classes)
            y_predict = []
            time_steps = []
            for idx in range(s):
                obs_time = []
                for pb in self.passbands:
                    if pb in self.orig_lc[idx]:
                        obs_time.append(self.orig_lc[idx][pb]['time'].values)
                obs_time = np.array(obs_time)
                obs_time = np.sort(obs_time[~np.isnan(obs_time)])
                y_predict_at_obstime = []
                for classnum, classname in enumerate(CLASS_NAMES):
                    y_predict_at_obstime.append(np.interp(obs_time, self.timesX[idx][:argmax[idx]], self.y_predict[idx][:, classnum][:argmax[idx]]))
                y_predict.append(np.array(y_predict_at_obstime).T)
                time_steps.append(obs_time + self.trigger_mjds[idx])
        else:
            y_predict = [self.y_predict[i][:argmax[i]] for i in range(nobjects)]
            time_steps = [self.timesX[i][:argmax[i]] + self.trigger_mjds[i] for i in range(nobjects)]

        return y_predict, time_steps

    def plot_light_curves_and_classifications(self, indexes_to_plot=None, step=True, use_interp_flux=False):
        """
        Plot light curve (top panel) and classifications (bottom panel) vs time.

        Parameters
        ----------
        indexes_to_plot : tuple
            The indexes listed in the tuple will be plotted according to the order of the input light curves.
            E.g. (0, 1, 3, 5) will plot the zeroth, first, third and fifth light curves and classifications.
            If None or True, then all light curves will be plotted
        step : bool
            Plot step function along data points instead of interpolating classifications between data.
        use_interp_flux : bool
            Use all 50 timesteps when plotting classification probabilities rather than just at the timesteps with data.

        """

        font = {'family': 'normal',
                'size': 33}
        matplotlib.rc('font', **font)

        if indexes_to_plot is None or indexes_to_plot is True:
            indexes_to_plot = np.arange(len(self.y_predict))

        if not hasattr(self, 'y_predict'):
            self.get_predictions()

        for idx in indexes_to_plot:
                argmax = self.timesX[idx].argmax() + 1
                fig, (ax1, ax2) = plt.subplots(nrows=2, ncols=1, figsize=(13, 15),
                                               num="classification_vs_time_{}".format(idx), sharex=True)
                # ax1.axvline(x=0, color='k', linestyle='-', linewidth=1)
                # ax2.axvline(x=0, color='k', linestyle='-', linewidth=1)

                for pb in self.passbands:
                    if pb in self.orig_lc[idx].keys():
                        ax1.errorbar(self.orig_lc[idx][pb]['time'], self.orig_lc[idx][pb]['flux'],
                                     yerr=self.orig_lc[idx][pb]['fluxErr'], fmt=PB_MARKER[pb], label=pb,
                                     c=PB_COLOR[pb], lw=3, markersize=10)

                new_t = np.array([self.orig_lc[idx][pb]['time'].values for pb in self.passbands]).flatten()
                new_t = np.sort(new_t[~np.isnan(new_t)])
                if not use_interp_flux:
                    new_y_predict = []
                    for classnum, classname in enumerate(CLASS_NAMES):
                        new_y_predict.append(np.interp(new_t, self.timesX[idx][:argmax], self.y_predict[idx][:, classnum][:argmax]))

                for classnum, classname in enumerate(CLASS_NAMES):
                    if not use_interp_flux:
                        if step:
                            ax2.step(new_t, new_y_predict[classnum], '-', label=classname, color=CLASS_COLOR[classname], linewidth=3, where='post')
                        else:
                            ax2.plot(new_t, new_y_predict[classnum], '-', label=classname, color=CLASS_COLOR[classname], linewidth=3,)
                    else:
                        ax2.plot(self.timesX[idx][:argmax], self.y_predict[idx][:, classnum][:argmax], '-', label=classname,
                             color=CLASS_COLOR[classname], linewidth=3)
                ax1.legend(frameon=True, fontsize=33)#, loc='lower right')
                ax2.legend(frameon=True, fontsize=21.5)#, loc='center right')  # , ncol=2)
                ax2.set_xlabel("Days since trigger (rest frame)")  # , fontsize=18)
                ax1.set_ylabel("Relative Flux")  # , fontsize=15)
                ax2.set_ylabel("Class Probability")  # , fontsize=18)
                # ax1.set_ylim(-0.1, 1.1)
                ax2.set_ylim(0, 1)
                ax1.set_xlim(left=min(new_t))  # ax1.set_xlim(-70, 80)
                # ax1.grid(True)
                # ax2.grid(True)
                plt.setp(ax1.get_xticklabels(), visible=False)
                ax2.yaxis.set_major_locator(MaxNLocator(nbins=6, prune='upper'))  # added
                plt.tight_layout()
                fig.subplots_adjust(hspace=0)
                savename = 'classification_vs_time_{}{}{}'.format(self.objids[idx], '_step' if step else '', '_no_interp' if not use_interp_flux else '')
                plt.savefig("{}.pdf".format(savename))
                # plt.savefig("{}.png".format(savename))
                plt.close()

        return self.orig_lc, self.timesX, self.y_predict

    def plot_classification_animation(self, indexes_to_plot=None):
        """ Plot light curve (top panel) and classifications (bottom panel) vs time as an mp4 animation.

        Parameters
        ----------
        indexes_to_plot : tuple
            The indexes listed in the tuple will be plotted according to the order of the input light curves.
            E.g. (0, 1, 3, 5) will plot the zeroth, first, third and fifth light curves and classifications.
            If None or True, then all light curves will be plotted

        """

        font = {'family': 'normal',
                'size': 33}
        matplotlib.rc('font', **font)

        if indexes_to_plot is None or indexes_to_plot is True:
            indexes_to_plot = np.arange(len(self.y_predict))

        if not hasattr(self, 'y_predict'):
            self.get_predictions()

        for idx in indexes_to_plot:
            new_t = np.array([self.orig_lc[idx][pb]['time'].values for pb in self.passbands]).flatten()
            all_flux = list(self.orig_lc[idx]['g']['flux']) + list(self.orig_lc[idx]['r']['flux'])

            argmax = self.timesX[idx].argmax() + 1
            fig, (ax1, ax2) = plt.subplots(nrows=2, ncols=1, figsize=(13, 15),
                                           num="animation_classification_vs_time_{}".format(idx), sharex=True)

            ax1.legend(frameon=False, fontsize=33)
            ax2.legend(frameon=False, fontsize=23.5)  # , ncol=2)
            ax2.set_xlabel("Days since trigger (rest frame)")  # , fontsize=18)
            ax1.set_ylabel("Relative Flux")  # , fontsize=15)
            ax2.set_ylabel("Class Probability")  # , fontsize=18)
            ax1.set_ylim(min(all_flux), max(all_flux))
            ax2.set_ylim(0, 1)
            ax1.set_xlim(min(new_t), max(new_t))  # ax1.set_xlim(-70, 80)
            plt.setp(ax1.get_xticklabels(), visible=False)
            ax2.yaxis.set_major_locator(MaxNLocator(nbins=6, prune='upper'))  # added
            plt.tight_layout()
            fig.subplots_adjust(hspace=0)
            ax1.axvline(x=0, color='k', linestyle='-', linewidth=1)
            ax2.axvline(x=0, color='k', linestyle='-', linewidth=1)

            Writer = animation.writers['ffmpeg']
            writer = Writer(fps=5, bitrate=1800)

            def animate(i):
                for pbidx, pb in enumerate(self.passbands):
                    ax1.plot(self.timesX[idx][:argmax][:int(i + 1)], self.X[idx][:, pbidx][:argmax][:int(i + 1)],
                             label=pb, c=PB_COLOR[pb], lw=3)  # , markersize=10, marker=MARKPB[pb])

                for classnum, classname in enumerate(CLASS_NAMES):
                    ax2.plot(self.timesX[idx][:argmax][:int(i + 1)],
                             self.y_predict[idx][:, classnum][:argmax][:int(i + 1)],
                             '-', label=classname, color=CLASS_COLOR[classname], linewidth=3)

                # Don't repeat legend items
                ax1.legend(frameon=False, fontsize=33)
                ax2.legend(frameon=False, fontsize=23.5)
                handles1, labels1 = ax1.get_legend_handles_labels()
                handles2, labels2 = ax2.get_legend_handles_labels()
                by_label1 = OrderedDict(zip(labels1, handles1))
                by_label2 = OrderedDict(zip(labels2, handles2))
                ax1.legend(by_label1.values(), by_label1.keys(), frameon=False, fontsize=33, loc='lower right')
                ax2.legend(by_label2.values(), by_label2.keys(), frameon=False, fontsize=21.5, loc='center right')

            ani = animation.FuncAnimation(fig, animate, frames=50, repeat=True)
            ani.save(os.path.join('classification_vs_time_{}.mp4'.format(self.objids[idx])), writer=writer)

    def plot_classification_animation_step(self, indexes_to_plot=None):
        """
        Plot light curve (top panel) and classifications (bottom panel) vs time as an mp4 animation
        as step function.

        Parameters
        ----------
        indexes_to_plot : tuple
            The indexes listed in the tuple will be plotted according to the order of the input light curves.
            E.g. (0, 1, 3, 5) will plot the zeroth, first, third and fifth light curves and classifications.
            If None or True, then all light curves will be plotted

        """

        font = {'family': 'normal',
                'size': 33}
        matplotlib.rc('font', **font)

        if indexes_to_plot is None or indexes_to_plot is True:
            indexes_to_plot = np.arange(len(self.y_predict))

        if not hasattr(self, 'y_predict'):
            self.get_predictions()

        for idx in indexes_to_plot:
            new_t = np.array([self.orig_lc[idx][pb]['time'].values for pb in self.passbands]).flatten()
            new_t = np.sort(new_t[~np.isnan(new_t)])
            new_y_predict = []
            all_flux = list(self.orig_lc[idx]['g']['flux']) + list(self.orig_lc[idx]['r']['flux'])

            argmax = self.timesX[idx].argmax() + 1
            fig, (ax1, ax2) = plt.subplots(nrows=2, ncols=1, figsize=(13, 15),
                                           num="animation_classification_vs_time_{}".format(idx), sharex=True)

            ax1.legend(frameon=False, fontsize=33)
            ax2.legend(frameon=False, fontsize=23.5)  # , ncol=2)
            ax2.set_xlabel("Days since trigger (rest frame)")  # , fontsize=18)
            ax1.set_ylabel("Relative Flux")  # , fontsize=15)
            ax2.set_ylabel("Class Probability")  # , fontsize=18)
            ax1.set_ylim(min(all_flux), max(all_flux))
            ax2.set_ylim(0, 1)
            ax1.set_xlim(min(new_t), max(new_t))
            plt.setp(ax1.get_xticklabels(), visible=False)
            ax2.yaxis.set_major_locator(MaxNLocator(nbins=6, prune='upper'))  # added
            plt.tight_layout()
            fig.subplots_adjust(hspace=0)
            ax1.axvline(x=0, color='k', linestyle='-', linewidth=1)
            ax2.axvline(x=0, color='k', linestyle='-', linewidth=1)

            Writer = animation.writers['ffmpeg']
            writer = Writer(fps=2, bitrate=1800)

            for classnum, classname in enumerate(CLASS_NAMES):
                new_y_predict.append(np.interp(new_t, self.timesX[idx][:argmax], self.y_predict[idx][:, classnum][:argmax]))

            def animate(i):
                for pbidx, pb in enumerate(self.passbands):
                    # ax1.plot(self.timesX[idx][:argmax][:int(i + 1)], self.X[idx][:, pbidx][:argmax][:int(i + 1)],
                    #          label=pb, c=PB_COLOR[pb], lw=3)  # , markersize=10, marker=MARKPB[pb])

                    # dea = [self.orig_lc[idx][pb]['time'] < self.timesX[idx][:argmax][int(i)]]
                    if i + 1 >= len(new_t):
                        break

                    dea = [self.orig_lc[idx][pb]['time'] < new_t[int(i+1)]]

                    ax1.errorbar(np.array(self.orig_lc[idx][pb]['time'])[dea], np.array(self.orig_lc[idx][pb]['flux'])[dea],
                                 yerr=np.array(self.orig_lc[idx][pb]['fluxErr'])[dea], fmt=PB_MARKER[pb], label=pb,
                                 c=PB_COLOR[pb], lw=3, markersize=10)

                for classnum, classname in enumerate(CLASS_NAMES):
                    # ax2.plot(self.timesX[idx][:argmax][:int(i + 1)],
                    #          self.y_predict[idx][:, classnum][:argmax][:int(i + 1)],
                    #          '-', label=classname, color=CLASS_COLOR[classname], linewidth=3)
                    ax2.step(new_t[:int(i + 1)],
                             new_y_predict[classnum][:int(i + 1)],
                             '-', label=classname, color=CLASS_COLOR[classname], linewidth=3, where='post')

                # Don't repeat legend items
                ax1.legend(frameon=False, fontsize=33)
                ax2.legend(frameon=False, fontsize=23.5)
                handles1, labels1 = ax1.get_legend_handles_labels()
                handles2, labels2 = ax2.get_legend_handles_labels()
                by_label1 = OrderedDict(zip(labels1, handles1))
                by_label2 = OrderedDict(zip(labels2, handles2))
                ax1.legend(by_label1.values(), by_label1.keys(), frameon=False, fontsize=33, loc='lower right')
                ax2.legend(by_label2.values(), by_label2.keys(), frameon=False, fontsize=21.5, loc='center right')

            ani = animation.FuncAnimation(fig, animate, frames=len(new_t), repeat=True)
            savename = 'classification_vs_time_{}_step'.format(self.objids[idx])
            ani.save("{}.mp4".format(savename), writer=writer)

