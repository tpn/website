# ===================================================================
# Imports
# ===================================================================
import dataclasses
import tiktoken
import torch
import torch.nn as nn
from torch.nn import functional as F

# ===================================================================
# Globals
# ===================================================================

# The following assumes you've created a notebook in the
# root of the parallelopedia repo, and you've downloaded
# the model_19072.pt file from HuggingFace per earlier
# instructions and placed it in the 'data' directory.
MODEL_CHECKPOINT = 'data/model_19072.pt'

# ===================================================================
# Setup
# ===================================================================

# Use bfloat16 for matmul precision where possible.
torch.set_float32_matmul_precision('high')

# ===================================================================
# GPT2 PyTorch Model Components
# ===================================================================

# Now define the classes making up our GPT2 implementation.
# These map directly to the components introduced by the
# now-seminal 2017 "Attention Is All You Need" paper.

class CausalSelfAttention(nn.Module):

    def __init__(self, config):
        super().__init__()
        assert config.n_embd % config.n_head == 0
        # Key, query, value projections for all heads, but in a batch.
        self.c_attn = nn.Linear(config.n_embd, 3 * config.n_embd)

        # Output projection.
        self.c_proj = nn.Linear(config.n_embd, config.n_embd)
        self.c_proj.NANOGPT_SCALE_INIT = 1

        # Regularization.
        self.n_head = config.n_head
        self.n_embd = config.n_embd

    def forward(self, x):
        # Batch size, sequence length, embedding dimensionality.
        B, T, C = (x.size())

        # Calculate query, key, values for all heads in
        # batch and move head forward to be the batch dim.
        #
        # N.B. nh is "number of heads", hs is "head size",
        #      and C (number of channels) is nh * hs.
        #      E.g. in GPT-2 (124M), n_head=12, hs=64, so
        #      nh*hs=C=768 channels in the Transformer.
        qkv = self.c_attn(x)
        q, k, v = qkv.split(self.n_embd, dim=2)

        head_dim = C // self.n_head

        # (B, nh, T, hs)
        k = k.view(B, T, self.n_head, head_dim).transpose(1, 2)

        # (B, nh, T, hs)
        q = q.view(B, T, self.n_head, head_dim).transpose(1, 2)

        # (B, nh, T, hs)
        v = v.view(B, T, self.n_head, head_dim).transpose(1, 2)

        # Flash attention.
        y = F.scaled_dot_product_attention(q, k, v, is_causal=True)

        # Re-assemble all head outputs side by side.
        y = (y.transpose(1, 2).contiguous().view(B, T, C))

        # Output projection.
        y = self.c_proj(y)
        return y


class MLP(nn.Module):

    def __init__(self, config):
        super().__init__()
        self.c_fc = nn.Linear(config.n_embd, 4 * config.n_embd)
        self.gelu = nn.GELU(approximate='tanh')
        self.c_proj = nn.Linear(4 * config.n_embd, config.n_embd)
        self.c_proj.NANOGPT_SCALE_INIT = 1

    def forward(self, x):
        x = self.c_fc(x)
        x = self.gelu(x)
        x = self.c_proj(x)
        return x


class Block(nn.Module):

    def __init__(self, config):
        super().__init__()
        self.ln_1 = nn.LayerNorm(config.n_embd)
        self.attn = CausalSelfAttention(config)
        self.ln_2 = nn.LayerNorm(config.n_embd)
        self.mlp = MLP(config)

    def forward(self, x):
        x = x + self.attn(self.ln_1(x))
        x = x + self.mlp(self.ln_2(x))
        return x

# ===================================================================
# GPT2 Supporting Classes
# ===================================================================

# N.B. These differ slightly from Andrej's classes in
#      `train_gpt2.py`.  `GPTCheckpoint` is a helper
#      class I wrote that has no analog in the former.

@dataclass
class GPTConfig:
    """
    Configuration class for GPT model.

    Attributes:

        block_size (int): Maximum sequence length.

        vocab_size (int): Number of tokens.  GPT2 from
            huggingface has a vocab size of 50257, which
            includes 50,000 BPE merges, 256 byte tokens,
            and 1 <|endoftext|> token.  However, Andrej
            Karpathy's `build-nanogpt/train_gpt2.py`
            uses a vocab size of 50304.  I vaguely recall
            the explanation for this discrepancy as a local
            optimization to yield better alignment sizes,
            but I'm not 100% certain.

            The local GPT2 training that we did on
            edu_fineweb10b used 50304, so we will use
            that here.

        n_layer (int): Number of layers.

        n_head (int): Number of attention heads.

        n_embd (int): Embedding dimension.
    """
    block_size: int = 1024
    vocab_size: int = 50304
    n_layer: int = 12
    n_head: int = 12
    n_embd: int = 768


@dataclass
class GPTCheckpoint:
    """
    Checkpoint class for GPT model.

    Mandatory Attributes:

        model (dict): The model state_dict.

        step (int): The step number.

        val_loss (float): The validation loss.

        config (GPTConfig): The configuration.
    """
    model: dict
    step: int
    val_loss: float
    config: GPTConfig

    @classmethod
    def load(cls,
             checkpoint_path: str,
             device: str) -> "GPTCheckpoint":
        """
        Load a checkpoint from a file.

        Args:

            checkpoint_path (str): Supplies the path to the
                checkpoint file.

            device (str): Supplies the device to use for
                the model.

        Returns:

            GPTCheckpoint: A new GPTCheckpoint instance.

        """
        data = torch.load(
            checkpoint_path,
            map_location=device,
        )
        checkpoint = cls(
            model=data["model"],
            step=data["step"],
            val_loss=data["val_loss"],
            config=GPTConfig(**data["config"]),
        )
        return checkpoint

    def save(self, checkpoint_path: str) -> None:
        """
        Save the checkpoint to a file.

        Args:

            checkpoint_path (str): Supplies the path to the
                checkpoint file.
        """
        # N.B. We save config as a raw dictionary to avoid
        #      pickling issues with object namespaces when
        #      reloading.
        data = {
            "model": self.model,
            "step": self.step,
            "val_loss": self.val_loss,
            "config": dataclasses.asdict(self.config),
        }
        torch.save(data, checkpoint_path)

