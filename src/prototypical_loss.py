# coding=utf-8
import torch
from torch.nn import functional as F
from torch.nn.modules import Module
from torch.nn.modules.loss import _assert_no_grad


class PrototypicalLoss(Module):
    '''
    Loss class deriving from Module for the prototypical loss function defined below
    '''

    def __init__(self, n_support):
        super(PrototypicalLoss, self).__init__()
        self.n_support = n_support

    def forward(self, input, target):
        _assert_no_grad(target)
        return prototypical_loss(input, target, self.n_support)


def euclidean_dist(x, y):
    '''
    Compute euclidean distance between two tensors
    '''
    # x: N x D
    # y: M x D
    n = x.size(0)
    m = y.size(0)
    d = x.size(1)
    if d != y.size(1):
        raise Exception

    x = x.unsqueeze(1).expand(n, m, d)
    y = y.unsqueeze(0).expand(n, m, d)

    return torch.pow(x - y, 2).sum(2)


def prototypical_loss(input, target, n_support):
    '''
    Inspired by https://github.com/jakesnell/prototypical-networks/blob/master/protonets/models/few_shot.py

    Compute the barycentres by averaging the features of n_support
    samples for each class in target, computes then the distances from each
    samples' features to each one of the barycentres, computes the
    log_probability for each n_query samples for each one of the current
    classes, of appartaining to a class c, loss and accuracy are then computed
    and returned
    Args:
    - input: the model output for a batch of samples
    - target: ground truth for the above batch of samples
    - n_support: number of samples to keep in account when computing
      barycentres, for each one of the current classes
    '''
    cputargs = target.cpu() if target.is_cuda else target

    def supp_idxs(c):
        # FIXME when torch will support where as np
        return (target == c).nonzero()[:n_support].squeeze()

    # FIXME when torch.unique will be available on cuda too
    classes = torch.unique(target.to('cpu')).to(target.device)
    n_classes = len(classes)
    # FIXME when torch will support where as np
    n_query = len((target == int(classes[0])).nonzero()) - n_support

    support_idxs = list(map(supp_idxs, classes))

    prototypes = torch.stack([input[i].mean(0) for i in support_idxs]).to(target.device)
    # FIXME when torch will support where as np
    query_idxs = torch.stack(list(map(lambda c: (cputargs == c).nonzero()[n_support:], classes))).view(-1).to(target.device)

    query_samples = input[query_idxs]
    dists = euclidean_dist(query_samples, prototypes)

    log_p_y = F.log_softmax(-dists, dim=1).view(n_classes, n_query, -1)

    target_inds = torch.arange(0, n_classes).to(target.device)
    target_inds = target_inds.view(n_classes, 1, 1)
    target_inds = target_inds.expand(n_classes, n_query, 1).long()

    loss_val = -log_p_y.gather(2, target_inds).squeeze().view(-1).mean()
    _, y_hat = log_p_y.max(2)
    acc_val = torch.eq(y_hat, target_inds.squeeze()).float().mean()

    return loss_val,  acc_val
