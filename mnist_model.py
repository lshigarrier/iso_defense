import torch
import torch.nn as nn
import torch.nn.functional as F


def compute_jacobian(data, output, device, num_stab=1e-4):
    c = output.shape[1]
    m = c - 1

    output = F.softmax(output, dim=1) * (1 - c * num_stab) + num_stab

    new_output = torch.sqrt(output)
    new_output = 2 * new_output[:, :m] / (1 - new_output[:, m].unsqueeze(1).repeat(1, m))

    jac = torch.zeros(m, *data.shape).to(device)
    grad_output = torch.zeros(*new_output.shape).to(device)
    for i in range(m):
        grad_output.zero_()
        grad_output[:, i] = 1
        jac[i] = torch.autograd.grad(new_output, data, grad_outputs=grad_output, retain_graph=True)[0]
    jac = torch.transpose(jac, dim0=0, dim1=1)
    return jac.contiguous().view(jac.shape[0], m, -1)


def get_jacobian_bound(output, epsilon):
    c = output.shape[1]
    m = c - 1
    delta = torch.sqrt(F.softmax(output, dim=1) / c).sum(dim=1)
    delta = 2 * torch.acos(delta)
    rho = (2 * (1 - torch.sqrt(output[:, m])) - output[:, :m].sum(dim=1)) / (1 - torch.sqrt(output[:, m]))
    return delta / (rho * epsilon)


class IsometryRegV2(nn.Module):

    def __init__(self, epsilon, num_stab=1e-4):
        super(IsometryRegV2, self).__init__()
        self.epsilon = epsilon
        self.num_stab = num_stab

    def forward(self, data, logits, device):
        # Input dimension
        n = data.shape[1]*data.shape[2]*data.shape[3]
        # Number of classes
        c = logits.shape[1]
        m = c - 1

        # Numerical stability
        probs = F.softmax(logits, dim=1)*(1 - c*self.num_stab) + self.num_stab
        # assert torch.all(output>0)

        # Coordinate change
        new_coord = torch.sqrt(probs)
        new_coord = 2 * new_coord[:, :m] / (1 - new_coord[:, m].unsqueeze(1).repeat(1, m))

        # Compute Jacobian matrix
        grad_output = torch.randn(*new_coord.shape).to(device)
        grad_output /= torch.norm(grad_output, dim=1).unsqueeze(-1)
        jac = torch.autograd.grad(new_coord, data, grad_outputs=grad_output, create_graph=True)[0]
        jac = jac.contiguous().view(jac.shape[0], -1)

        # Estimation of the trace of JJ^T
        jac = torch.norm(jac, dim=1)

        # Distance from center of simplex
        delta = torch.sqrt(probs / c).sum(dim=1)
        delta = 2 * torch.acos(delta)

        # Compute regularization term
        reg = torch.norm(torch.add(jac,-delta/self.epsilon))

        # Return
        return reg.mean(), torch.tensor(0)


class IsometryReg(nn.Module):

    def __init__(self, epsilon, num_stab=1e-4):
        super(IsometryReg, self).__init__()
        self.epsilon = epsilon
        self.num_stab = num_stab

    def forward(self, data, logits, device):
        # Input dimension
        n = data.shape[1]*data.shape[2]*data.shape[3]
        # Number of classes
        c = logits.shape[1]
        m = c - 1

        # Numerical stability
        probs = F.softmax(logits, dim=1)*(1 - c*self.num_stab) + self.num_stab
        # assert torch.all(output>0)

        # Coordinate change
        new_coord = torch.sqrt(probs)
        new_coord = 2 * new_coord[:, :m] / (1 - new_coord[:, m].unsqueeze(1).repeat(1, m))

        # Compute Jacobian matrix
        jac = torch.zeros(m, *data.shape).to(device)
        grad_output = torch.zeros(*new_coord.shape).to(device)
        for i in range(m):
            grad_output.zero_()
            grad_output[:, i] = 1
            jac[i] = torch.autograd.grad(new_coord, data, grad_outputs=grad_output, retain_graph=True)[0]
        jac = torch.transpose(jac, dim0=0, dim1=1)
        jac = jac.contiguous().view(jac.shape[0], jac.shape[1], -1)

        # Gram matrix of Jacobian
        jac = torch.bmm(jac, torch.transpose(jac, 1, 2))

        # Compute the FIM coefficient in stereographic projection
        coeff = 4 * (1 - torch.sqrt(probs[:, m])) ** 2

        # Distance from center of simplex
        delta = torch.sqrt(probs / c).sum(dim=1)
        delta = 2 * torch.acos(delta)

        # Rescaled identity matrix
        factor = (delta ** 2 / coeff / self.epsilon ** 2).view(-1, 1, 1)
        identity = factor * torch.eye(m).unsqueeze(0).repeat(logits.shape[0], 1, 1).to(device)

        # Compute regularization term (alpha in docs)
        reg = torch.linalg.norm((jac - identity).contiguous().view(len(data), -1), dim=1) / n

        # Return
        return reg.mean(), torch.tensor(0)
'''
        # Input dimension
        n = data.shape[1]*data.shape[2]*data.shape[3]
        # Number of classes
        c = output.shape[1]
        m = c - 1

        # Numerical stability
        output = F.softmax(output, dim=1)*(1 - c*self.num_stab) + self.num_stab
        # assert torch.all(output>0)

        # Coordinate change
        new_output = torch.sqrt(output)
        new_output = 2 * new_output[:, :m] / (1 - new_output[:, m].unsqueeze(1).repeat(1, m))

        # Compute Jacobian matrix
        jac = torch.zeros(m, *data.shape).to(device)
        grad_output = torch.zeros(*new_output.shape).to(device)
        for i in range(m):
            grad_output.zero_()
            grad_output[:, i] = 1
            jac[i] = torch.nan_to_num(torch.autograd.grad(new_output, data, grad_outputs=grad_output, retain_graph=True)[0])
        jac = torch.transpose(jac, dim0=0, dim1=1)
        jac = jac.contiguous().view(jac.shape[0], jac.shape[1], -1)

        # Gram matrix of Jacobian
        jac = torch.bmm(jac, torch.transpose(jac, 1, 2))

        # Compute the change of basis matrix
        change = output[:, m] / torch.square(
            2 * torch.sqrt(output[:, m]) - torch.norm(output[:, :c-1], p=1, dim=1))

        # Distance from center of simplex
        delta = torch.sqrt(output / c).sum(dim=1)
        delta = 2 * torch.acos(delta)

        # Diagonal embedding
        change = torch.diag_embed(change.unsqueeze(1).repeat(1, m))
        change = change * (delta ** 2)[:, None, None]
        change = change / self.epsilon ** 2

        # Compute regularization term (alpha in docs)
        reg = self.epsilon**2/n*torch.linalg.norm((jac - change).contiguous().view(len(data), -1), dim=1)

        # Return
        return reg.mean(), torch.tensor(0)
        # return reg.mean(), torch.tensor(0), torch.tensor(0), torch.tensor(0), torch.tensor(0)
'''


class JacobianReg(nn.Module):

    def __init__(self, epsilon, barrier='relu', num_stab=1e-4):
        super(JacobianReg, self).__init__()
        self.epsilon = epsilon
        self.num_stab = num_stab
        # Barrier function
        if barrier == 'relu':
            self.barrier = F.relu
        elif barrier == 'elu':
            self.barrier = F.elu
        elif barrier == 'exp':
            self.barrier = torch.exp
        else:
            raise NotImplementedError

    def forward(self, data, output, device):
        # Input dimension
        # n = data.shape[2]*data.shape[3]
        # Number of classes
        c = output.shape[1]
        m = c - 1

        # Numerical stability
        output = F.softmax(output, dim=1)*(1 - c*self.num_stab) + self.num_stab
        # assert torch.all(output>0)

        # Coordinate change
        new_output = torch.sqrt(output)
        new_output = 2 * new_output[:, :m] / (1 - new_output[:, m].unsqueeze(1).repeat(1, m))

        # Compute Jacobian matrix
        jac = torch.zeros(m, *data.shape).to(device)
        grad_output = torch.zeros(*new_output.shape).to(device)
        for i in range(m):
            grad_output.zero_()
            grad_output[:, i] = 1
            jac[i] = torch.autograd.grad(new_output, data, grad_outputs=grad_output, retain_graph=True)[0]
        jac = torch.transpose(jac, dim0=0, dim1=1)
        jac = jac.contiguous().view(jac.shape[0], m, -1)

        # Compute delta and rho
        delta = torch.sqrt(output/c).sum(dim=1)
        delta = 2*torch.acos(delta)
        # rho = (2*(1-torch.sqrt(output[:, m])) - output[:, :m].sum(dim=1))/(1-torch.sqrt(output[:, m]))
        rho = 1 - torch.sqrt(output[:, m])
        bound = delta/(rho*self.epsilon)

        # Frobenius norm
        # jac_flat = jac.contiguous().view(jac.shape[0], -1)
        # jac_norm_frob = torch.square(jac_flat).sum(dim=1)

        # Holder inequality
        abs_jac = torch.abs(jac)
        norm_1 = torch.max(abs_jac.sum(dim=1, keepdim=True), dim=2)[0]
        norm_inf = torch.max(abs_jac.sum(dim=2, keepdim=True), dim=1)[0]
        jac_norm_holder = torch.sqrt(norm_1 * norm_inf)

        # Exact computation
        # max_eig_val = torch.lobpcg(torch.bmm(jac, jac.transpose(1,2)), k=1, largest=True)[0]
        # jac_norm = torch.sqrt(max_eig_val.squeeze())

        # Compute regularization
        reg = self.barrier(jac_norm_holder - bound)
        return reg.mean(), jac_norm_holder.mean()
        # return reg.mean(), jac_norm.mean(), jac_norm_holder.mean(), jac_norm_frob.mean(), bound.mean()


class Lenet(nn.Module):

    def __init__(self, param, perform_softmax=False):
        super(Lenet, self).__init__()
        self.conv1 = nn.Conv2d(1, param['channels1'], 3, 1)
        self.conv2 = nn.Conv2d(param['channels1'], param['channels2'], 3, 1)
        # self.dropout1 = nn.Dropout(0.25)
        # self.dropout2 = nn.Dropout(0.5)
        self.fc1 = nn.Linear(9216, param['hidden'])
        self.fc2 = nn.Linear(param['hidden'], 10)
        self.perform_softmax = perform_softmax

    def forward(self, x):
        x = self.conv1(x)
        x = F.relu(x)
        x = self.conv2(x)
        x = F.relu(x)
        x = F.max_pool2d(x, 2)
        # x = self.dropout1(x)
        x = torch.flatten(x, 1)
        x = self.fc1(x)
        x = F.relu(x)
        # x = self.dropout2(x)
        logits = self.fc2(x)
        if self.perform_softmax:
            softmax_output = F.softmax(logits, dim=1)
            return softmax_output
        else:
            return logits
