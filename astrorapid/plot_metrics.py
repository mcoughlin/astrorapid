import os
import numpy as np
import pandas as pd
from distutils.spawn import find_executable
from scipy.interpolate import interp1d
from keras.utils import to_categorical
from sklearn.metrics import confusion_matrix

from astrorapid.classifier_metrics import plot_confusion_matrix, compute_multiclass_roc_auc, compute_precision_recall, \
    plasticc_log_loss

try:
    import matplotlib.pyplot as plt
    import matplotlib
    from matplotlib.ticker import MaxNLocator
    import imageio
    if find_executable('latex'):
        plt.rcParams['text.usetex'] = True
    plt.rcParams['font.serif'] = ['Computer Modern Roman'] + plt.rcParams['font.serif']

except ImportError:
    print("Warning: You will need to install 'matplotlib' and 'imageio' if you want to plot the "
          "classification performance metrics.")

COLORS = ['grey', 'tab:green', 'tab:orange', 'tab:blue', 'tab:red', 'tab:purple', 'tab:brown', '#aaffc3', 'tab:olive',
          'tab:cyan', '#FF1493', 'navy', 'tab:pink', 'lightcoral', '#228B22', '#aa6e28', '#FFA07A']
COLCLASS = {'Pre-explosion': 'grey', 'SNIa-norm': 'tab:green', 'SNIbc': 'tab:orange', 'SNII': 'tab:blue',
            'SNIa-91bg': 'tab:red', 'SNIa-x': 'tab:purple', 'point-Ia': 'tab:brown', 'Kilonova': '#aaffc3',
            'SLSN-I': 'tab:olive', 'PISN': 'tab:cyan', 'ILOT': '#FF1493', 'CART': 'navy', 'TDE': 'tab:pink'}
COLPB = {'u': 'tab:blue', 'g': 'tab:blue', 'r': 'tab:orange', 'i': 'm', 'z': 'k', 'Y': 'y'}
MARKPB = {'g': 'o', 'r': 's'}
ALPHAPB = {'g': 0.3, 'r': 1.}
WLOGLOSS_WEIGHTS = [1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2]


def plot_metrics(class_names, model, X_test, y_test, fig_dir, timesX_test=None, orig_lc_test=None, objids_test=None,
                 passbands=('g', 'r')):
    scores = model.evaluate(X_test, y_test, verbose=0)
    print("Accuracy: %.2f%%" % (scores[1] * 100))

    y_pred = model.predict(X_test)
    y_test_indexes = np.argmax(y_test, axis=-1)
    y_pred_indexes = np.argmax(y_pred, axis=-1)

    accuracy = len(np.where(y_pred_indexes == y_test_indexes)[0])
    print("Accuracy is: {}/{} = {}".format(accuracy, len(y_test_indexes.flatten()),
                                           accuracy / len(y_test_indexes.flatten())))

    class_names = ["Pre-explosion"] + class_names

    timesX_test[timesX_test == 0] = -200

    for cname in class_names:
        dirname = os.path.join(fig_dir + '/lc_pred', cname)
        if not os.path.exists(dirname):
            os.makedirs(dirname)

    # Plot accuracy vs time per class
    font = {'family': 'normal',
            'size': 36}
    matplotlib.rc('font', **font)

    # Plot classification example vs time
    for idx in np.arange(0, 100):
        print("Plotting example vs time", idx)
        argmax = timesX_test[idx].argmax() + 1
        fig, (ax1, ax2) = plt.subplots(nrows=2, ncols=1, figsize=(13, 15), num="classification_vs_time_{}".format(idx),
                                       sharex=True)

        for pb in passbands:
            if pb in orig_lc_test[idx].keys():
                try:
                    ax1.errorbar(orig_lc_test[idx][pb]['time'], orig_lc_test[idx][pb]['flux'],
                                 yerr=orig_lc_test[idx][pb]['fluxErr'], fmt=MARKPB[pb], label=pb, c=COLPB[pb],
                                 lw=3, markersize=10)
                except KeyError:
                    ax1.errorbar(orig_lc_test[idx][pb]['time'], orig_lc_test[idx][pb][5], yerr=orig_lc_test[idx][pb][6],
                                 fmt=MARKPB[pb], label=pb, c=COLPB[pb], lw=3, markersize=10)
        true_class = int(max(y_test_indexes[idx]))
        t0 = orig_lc_test[idx]['otherinfo'].values.flatten()[0]
        ax1.axvline(x=t0, color='grey', linestyle='--', linewidth=2)
        ax2.axvline(x=t0, color='grey', linestyle='--', linewidth=2)
        ax1.axvline(x=0, color='k', linestyle='-', linewidth=1)
        ax2.axvline(x=0, color='k', linestyle='-', linewidth=1)
        try:
            otherinfo = orig_lc_test[idx]['otherinfo'].values.flatten()
            t0, redshift, mwebv, b, peakmag, ra, decl, trigger_mjd, peakmjd = otherinfo[0:9]
            print(otherinfo[0:9])
            ax1.axvline(x=peakmjd - trigger_mjd, color='k', linestyle=':', linewidth=1)
            ax2.axvline(x=peakmjd - trigger_mjd, color='k', linestyle=':', linewidth=1)
        except Exception as e:
            print(e)

        ax1.annotate('$t_0 = {}$'.format(round(t0, 1)), xy=(t0, 1), xytext=(t0 - 33, 0.9), color='grey')
        class_accuracies = [timesX_test[idx][:argmax]]

        for classnum, classname in enumerate(class_names):
            ax2.plot(timesX_test[idx][:argmax], y_pred[idx][:, classnum][:argmax], '-', label=classname,
                     color=COLORS[classnum], linewidth=3)
            class_accuracies.append(y_pred[idx][:, classnum][:argmax])
        ax1.legend(frameon=False, fontsize=33)
        ax2.legend(frameon=False, fontsize=23.5)  # , ncol=2)
        ax2.set_xlabel("Days since trigger (rest frame)")  # , fontsize=18)
        ax1.set_ylabel("Relative Flux")  # , fontsize=15)
        ax2.set_ylabel("Class Probability")  # , fontsize=18)
        # ax1.set_ylim(-0.1, 1.1)
        # ax2.set_ylim(0, 1)
        ax1.set_xlim(-70, 80)
        plt.setp(ax1.get_xticklabels(), visible=False)
        ax2.yaxis.set_major_locator(MaxNLocator(nbins=6, prune='upper'))  # added
        plt.tight_layout()
        fig.subplots_adjust(hspace=0)
        plt.savefig(os.path.join(fig_dir + '/lc_pred',
                                 "classification_vs_time_{}_{}_{}_{}.pdf".format(idx, class_names[true_class], redshift,
                                                                                 peakmjd - trigger_mjd)))
        plt.savefig(os.path.join(fig_dir + '/lc_pred', class_names[true_class],
                                 "classification_vs_time_{}_{}_{}_{}.pdf".format(idx, class_names[true_class], redshift,
                                                                                 peakmjd - trigger_mjd)))

    print("Plotting Accuracy vs time per class...")
    fig = plt.figure("accuracy_vs_time_perclass", figsize=(13, 12))
    # fig = plt.figure(figsize=(13, 12))
    for classnum, classname in enumerate(class_names):
        correct_predictions_inclass = (y_test_indexes == classnum) & (y_pred_indexes == y_test_indexes)
        time_bins = np.arange(-150, 150, 3.)

        times_binned_indexes = np.digitize(timesX_test, bins=time_bins, right=True)
        time_list_indexes_inclass, count_correct_vs_binned_time_inclass = np.unique(times_binned_indexes * correct_predictions_inclass, return_counts=True)
        time_list_indexes2_inclass, count_objects_vs_binned_time_inclass = np.unique(times_binned_indexes * (y_test_indexes == classnum), return_counts=True)

        time_list_indexes_inclass = time_list_indexes_inclass[time_list_indexes_inclass < len(time_bins)]
        count_correct_vs_binned_time_inclass = count_correct_vs_binned_time_inclass[time_list_indexes_inclass < len(time_bins)]
        time_list_indexes2_inclass = time_list_indexes2_inclass[time_list_indexes2_inclass < len(time_bins)]
        count_objects_vs_binned_time_inclass = count_objects_vs_binned_time_inclass[time_list_indexes2_inclass < len(time_bins)]

        start_time_index = int(np.where(time_list_indexes2_inclass == time_list_indexes_inclass[1])[0])
        end_time_index = int(np.where(time_list_indexes2_inclass == time_list_indexes_inclass[-1])[0]) + 1

        try:
            accuracy_vs_time_inclass = count_correct_vs_binned_time_inclass[1:] / count_objects_vs_binned_time_inclass[start_time_index:end_time_index]
        except Exception as e:
            print(e)
            continue

        try:
            assert np.all(time_list_indexes_inclass[1:] == time_list_indexes2_inclass[start_time_index:end_time_index])
        except Exception as e:
            import pdb; pdb.set_trace()
            print(e)
            pass

        plt.plot(time_bins[time_list_indexes_inclass[1:]], accuracy_vs_time_inclass, '-', label=classname, color=COLORS[classnum], lw=3)
    plt.xlim(left=-35, right=70)
    plt.xlabel("Days since trigger (rest frame)")
    plt.ylabel("Classification accuracy")
    plt.legend(frameon=True, fontsize=25, ncol=2, loc=0)  # , bbox_to_anchor=(0.05, -0.1))
    plt.tight_layout()
    plt.savefig(os.path.join(fig_dir, "accuracy_vs_time_perclass.pdf"), bbox_inches='tight')
    plt.close()

    font = {'family': 'normal',
            'size': 33}

    matplotlib.rc('font', **font)

    # Plot confusion matrix at different days past trigger
    print("Plotting Confusion Matrices...")
    time_bins = np.arange(-110, 110, 1.)
    nobjects = len(timesX_test)
    ntimesteps = len(time_bins)
    nclasses = y_test.shape[-1]
    y_test_indexes_days_past_trigger = np.zeros((nobjects, ntimesteps))
    y_pred_indexes_days_past_trigger = np.zeros((nobjects, ntimesteps))
    y_pred_days_past_trigger = np.zeros((nobjects, ntimesteps, nclasses))
    for objidx in range(nobjects):
        print(objidx, nobjects, 'For conf matrix') if objidx % 1000 == 0 else 0
        f = interp1d(timesX_test[objidx], y_test_indexes[objidx], kind='nearest', bounds_error=False,
                     fill_value='extrapolate')
        y_test_indexes_days_past_trigger[objidx][:] = f(time_bins)
        f = interp1d(timesX_test[objidx], y_pred_indexes[objidx], kind='nearest', bounds_error=False,
                     fill_value='extrapolate')
        y_pred_indexes_days_past_trigger[objidx][:] = f(time_bins)
        for classidx in range(nclasses):
            classprob = y_pred[objidx][:, classidx]
            mintimeidx = 0
            maxtimeidx = np.argmax(timesX_test[objidx])
            f = interp1d(timesX_test[objidx], classprob, kind='linear', bounds_error=False,
                         fill_value=(classprob[mintimeidx], classprob[maxtimeidx]))
            y_pred_days_past_trigger[objidx][:, classidx][:] = f(time_bins)

    images_cf, images_roc, images_pr = [], [], []
    roc_auc, pr_auc = {}, {}
    wlogloss = {}
    for i, days_since_trigger in enumerate(list(np.arange(-25, 25)) + list(np.arange(25, 70, step=5))):  # [('early2days', 2), ('late40days', 40)]: # [-25, -20, -15, -10, -5, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70]:
        print("Plotting CF matrix", i, days_since_trigger, "days")
        index = np.where(time_bins == days_since_trigger)[0][0]
        y_test_on_day_i = y_test_indexes_days_past_trigger[:, index]
        y_pred_on_day_i = y_pred_indexes_days_past_trigger[:, index]
        y_pred_prob_on_day_i = y_pred_days_past_trigger[:, index]

        name = 'since_trigger_{}'.format(days_since_trigger)
        title = '{} days since trigger'.format(days_since_trigger)
        cnf_matrix = confusion_matrix(y_test_on_day_i, y_pred_on_day_i)
        print(name, cnf_matrix)
        figname_cf = plot_confusion_matrix(cnf_matrix, classes=class_names, normalize=True, title=title,
                                           fig_dir=fig_dir + '/cf_since_trigger', name=name)
        images_cf.append(imageio.imread(figname_cf))

        figname_roc, roc_auc[days_since_trigger] = compute_multiclass_roc_auc(class_names,
                                                                              to_categorical(y_test_on_day_i,
                                                                                             num_classes=nclasses),
                                                                              y_pred_prob_on_day_i, name=name,
                                                                              fig_dir=fig_dir + '/roc_since_trigger',
                                                                              title=title)
        images_roc.append(imageio.imread(figname_roc))

        figname_pr, pr_auc[days_since_trigger] = compute_precision_recall(class_names, to_categorical(y_test_on_day_i,
                                                                                                      num_classes=nclasses),
                                                                          y_pred_prob_on_day_i, name=name,
                                                                          fig_dir=fig_dir + '/pr_since_trigger',
                                                                          title=title)
        images_pr.append(imageio.imread(figname_pr))

        wlogloss[days_since_trigger] = plasticc_log_loss(to_categorical(y_test_on_day_i, num_classes=nclasses),
                                                         y_pred_prob_on_day_i, relative_class_weights=WLOGLOSS_WEIGHTS)

        plt.close()

        objids_filename = os.path.join(fig_dir + '/truth_table_since_trigger', 'objids_{}.csv'.format(name))
        predicted_table_filename = os.path.join(fig_dir + '/truth_table_since_trigger',
                                                'predicted_prob_{}.csv'.format(name))
        truth_table_filename = os.path.join(fig_dir + '/truth_table_since_trigger', 'truth_table_{}.csv'.format(name))
        np.savetxt(objids_filename, objids_test, fmt='%s')
        np.savetxt(predicted_table_filename, y_pred_prob_on_day_i)
        np.savetxt(truth_table_filename, to_categorical(y_test_on_day_i, num_classes=nclasses))
        # out_objtable = os.path.join(fig_dir + '/truth_table_since_trigger', 'out_obj_table_{}.txt'.format(name))
        # out_truth = os.path.join(fig_dir + '/truth_table_since_trigger', 'out_truth_{}.csv'.format(name))
        # out_pred = os.path.join(fig_dir + '/truth_table_since_trigger', 'out_pred_{}.csv'.format(name))
        # make_tables(objids_filename, predicted_table_filename, truth_table_filename, directory='', processes=2, out_objtable=out_objtable, out_truth=out_truth, out_pred=out_pred)

    imageio.mimsave(os.path.join(fig_dir, 'animation_cf_since_trigger.gif'), images_cf, duration=0.25)
    imageio.mimsave(os.path.join(fig_dir, 'animation_roc_since_trigger.gif'), images_roc, duration=0.25)
    imageio.mimsave(os.path.join(fig_dir, 'animation_pr_since_trigger.gif'), images_pr, duration=0.25)

    font = {'family': 'normal',
            'size': 36}

    matplotlib.rc('font', **font)

    # Plot ROC AUC vs time
    plt.figure("ROC AUC vs time", figsize=(13, 12))
    roc_auc = pd.DataFrame(roc_auc).transpose()
    names = list(roc_auc.keys())

    plt.plot(list(roc_auc['micro'].index), list(roc_auc['micro'].values), color='navy', linestyle=':', linewidth=4,
             label='micro-average')
    for classnum, classname in enumerate(class_names):
        if classname not in names or classnum == 0:
            print(classname)
            continue
        times = list(roc_auc[classname].index)
        aucs = list(roc_auc[classname].values)
        plt.plot(times, aucs, '-', label=classname, color=COLORS[classnum], linewidth=4)

    plt.legend(frameon=True, fontsize=25)
    plt.xlabel("Days since trigger (rest frame)")  # , fontsize=18)
    plt.ylabel("AUC")  # , fontsize=15)
    plt.tight_layout()
    plt.savefig(os.path.join(fig_dir, "auc_roc_vs_time.pdf"))
    plt.close()

    # # Plot Precision AUC vs time
    # plt.figure("ROC AUC vs time", figsize=(12, 11))
    # pr_auc = pd.DataFrame(pr_auc).transpose()
    # names = list(pr_auc.keys())
    # plt.plot(list(pr_auc['micro'].index), list(pr_auc['micro'].values), color='navy', linestyle=':', linewidth=4, label='micro')
    # for classnum, classname in enumerate(class_names):
    #     if classname not in names or classnum == 0:
    #         print(classname)
    #         continue
    #     times = list(pr_auc[classname].index)
    #     aucs = list(pr_auc[classname].values)
    #     plt.plot(times, aucs, '-', label=classname, color=COLORS[classnum], linewidth=2)
    #
    # plt.legend(frameon=False, fontsize=19)
    # plt.xlabel("Days since trigger")  # , fontsize=18)
    # plt.ylabel("AUC")  # , fontsize=15)
    # plt.savefig(os.path.join(fig_dir, "auc_pr_vs_time.pdf"))
    # plt.close()

    font = {'family': 'normal',
            'size': 36}
    matplotlib.rc('font', **font)

    # Plot weighted log loss vs time
    plt.figure("Weighted log loss vs time", figsize=(13, 12))
    plt.plot(list(wlogloss.keys()), list(wlogloss.values()), linewidth=4, label='Weighted Log loss')
    plt.xlabel("Days since trigger (rest frame)")  # , fontsize=18)
    plt.ylabel("Weighted log loss")  # , fontsize=15)
    plt.tight_layout()
    plt.savefig(os.path.join(fig_dir, "wlogloss_vs_time.pdf"))
    plt.close()
    print(wlogloss)
