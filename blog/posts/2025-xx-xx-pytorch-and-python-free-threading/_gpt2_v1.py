# ===================================================================
# Imports
# ===================================================================
import dataclasses
import logging

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

LOG_LEVEL = 'DEBUG'

# ===================================================================
# Logging
# ===================================================================
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(levelname)s - %(message)s',
)

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
    """
    Causal self-attention for the GPT2 model.
    """

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
    """
    Multi-layer perceptron for the GPT2 model.
    """

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
    """
    Transformer block for the GPT2 model.
    """

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

# ===================================================================
# GPT2 Model Implementation
# ===================================================================

class GPT(nn.Module):

    def __init__(self, config):
        super().__init__()
        self.config = config

        self.transformer = nn.ModuleDict(
            dict(
                wte=nn.Embedding(config.vocab_size, config.n_embd),
                wpe=nn.Embedding(config.block_size, config.n_embd),
                h=nn.ModuleList(
                    [Block(config) for _ in range(config.n_layer)]
                ),
                ln_f=nn.LayerNorm(config.n_embd),
            )
        )
        self.lm_head = nn.Linear(
            config.n_embd, config.vocab_size, bias=False
        )

        self.transformer.wte.weight = self.lm_head.weight
        self.apply(self._init_weights)

    def _init_weights(self, module):
        if isinstance(module, nn.Linear):
            std = 0.02
            if hasattr(module, "NANOGPT_SCALE_INIT"):
                std *= (2 * self.config.n_layer) ** -0.5
            torch.nn.init.normal_(module.weight, mean=0.0, std=std)
            if module.bias is not None:
                torch.nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)

    def forward(self, idx, targets=None):
        """
        Forward pass of the GPT model.

        Args:
            idx (torch.Tensor): Supplies the input tensor of shape
                (B, T).
            targets (torch.Tensor): Optionally supplies the target
                tensor of shape (B, T) for computing the loss.

        """
        (B, T) = idx.size()

        # Forward the token and position embeddings.

        # Shape (T)
        pos = torch.arange(0, T, dtype=torch.long, device=idx.device)

        # Position embeddings of shape (T, n_embd).
        pos_emb = self.transformer.wpe(pos)

        # Token embeddings of shape (B, T, n_embd).
        tok_emb = self.transformer.wte(idx)

        x = tok_emb + pos_emb

        # Forward the blocks of the transformer.
        for block in self.transformer.h:
            x = block(x)

        # Forward the final layernorm and the classifier.
        x = self.transformer.ln_f(x)

        # (B, T, vocab_size)
        logits = self.lm_head(x)

        loss = None
        if targets is not None:
            loss = F.cross_entropy(
                logits.view(-1, logits.size(-1)), targets.view(-1)
            )

        return (logits, loss)

    @classmethod
    def from_local_pretrained(
        cls, model_path: str, map_location: str = "cpu"
    ):
        """
        Load a model from a local checkpoint.

        N.B. This is a new method based off GPT.from_pretrained
             in Andrej Karpathy's train_gpt2.py.

        Args:
            cls (type): Supplies the class type.

            model_path (str): Supplies the path to the model
                checkpoint.

            map_location (str): Supplies the device to which
                the model will be mapped.
        """
        with torch.serialization.safe_globals([GPTConfig]):
            checkpoint = torch.load(
                model_path,
                map_location=map_location,
            )

        config = checkpoint["config"]
        model = cls(config)
        model.load_state_dict(checkpoint["model"])
        model.eval()

        msg = (
            f"Loaded model from step {checkpoint['step']}, "
            f"val_loss {checkpoint['val_loss']}"
        )
        logging.info(msg)
        return model

    def generate(
        self, text: str, max_length: int = 1024, top_k: int = 50,
        seed: int = None,
    ) -> str:
        """
        Generate text from the model.

        N.B. This is a new method based off the generation code
             present in Andrej Karpathy's train_gpt2.py.

        Args:

            text (str): Supplies the prompt.

            max_length (int): Supplies the maximum total length,
                including prompt.

            top_k (int): Supplies the number of tokens to consider
                at each generation step.

            seed (int): Optionally supplies the manual seed to use
                for the generator.  If None, the model's manual
                seed will be used.

        Returns:

            str: The generated text (including the initial prompt).
        """
        self.eval()
        # Obtain our GPT2 tokenizer, and resolve the stop token.
        enc = tiktoken.get_encoding("gpt2")
        stop_string = '<|endoftext|>'
        stop_token = enc.n_vocab - 1
        actual = enc.decode([stop_token])
        assert actual == stop_string, (
            f"expected {stop_string}, got {actual}"
        )

        # Encode the prompt.
        tokens = enc.encode(text)
        x = torch.tensor(
            tokens, dtype=torch.long, device=device
        ).unsqueeze(0)

        # Create a random generator for reproducibility.
        if seed is None:
            seed = self.manual_seed
        sample_rng = torch.Generator(device=device)
        sample_rng.manual_seed(seed)

        # Generate tokens up to our max length, or until we hit the
        # stop token.
        start = time.perf_counter()
        count = 0
        while x.size(1) < max_length:
            count += 1
            with torch.no_grad():
                # Forward pass, ignoring the returned loss.
                (logits, _) = self(x)

            # Take the logits at the last time-step (shape:
            # (1, vocab_size)).
            logits = logits[:, -1, :]

            # Convert to probabilities.
            probs = F.softmax(logits, dim=-1)

            # Top-k sampling.
            topk_probs, topk_indices = torch.topk(
                probs, k=top_k, dim=-1
            )

            # Sample the next token.
            next_idx = torch.multinomial(
                topk_probs, num_samples=1, generator=sample_rng
            )
            next_token = torch.gather(topk_indices, -1, next_idx)

            # If the next token is the stop token, we're done.
            if next_token.item() == stop_token:
                break

            # Otherwise, append the token to the current sequence
            # and continue generation.
            x = torch.cat((x, next_token), dim=1)

        end = time.perf_counter()
        elapsed = end - start
        tokens_per_sec = float(count) / elapsed

        msg = (
            f'Generated {count} tokens in {elapsed:.2f} seconds '
            f'({tokens_per_sec:.2f} tokens/sec)'
        )
        logging.debug(msg)

        # Decode the output tokens and return the generated text,
        # including the initial prompt.
        output_tokens = x[0].tolist()
        return enc.decode(output_tokens)

