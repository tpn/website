class CausalSelfAttention(nn.Module):

    def __init__(self, config):
        super().__init__()
        assert config.n_embd % config.n_head == 0
        # Key, query, value projections for all heads, but in a batch.
        self.c_attn = NoInitLinear(config.n_embd, 3 * config.n_embd)

        # Output projection.
        self.c_proj = NoInitLinear(config.n_embd, config.n_embd)
        self.c_proj.NANOGPT_SCALE_INIT = 1

        # Regularization.
        self.n_head = config.n_head
        self.n_embd = config.n_embd

    def forward(self, x):
        # Batch size, sequence length, embedding dimensionality.
        B, T, C = (x.size())

        # Calculate query, key, values for all heads in batch and move head
        # forward to be the batch dim.
        #
        # N.B. nh is "number of heads", hs is "head size", and C (number of
        #      channels) is nh * hs.  E.g. in GPT-2 (124M), n_head=12, hs=64,
        #      so nh*hs=C=768 channels in the Transformer.
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


# Multi-Layer Perceptron
class MLP(nn.Module):

    def __init__(self, config):
        super().__init__()
        self.c_fc = NoInitLinear(config.n_embd, 4 * config.n_embd)
        self.gelu = nn.GELU(approximate='tanh')
        self.c_proj = NoInitLinear(4 * config.n_embd, config.n_embd)
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


class GPT(nn.Module):

    ...

    def generate(
        self, text: str, max_length: int = 1024, top_k: int = 50,
        seed: int = None, save_rate: callable = None
    ) -> str:
        """
        Generate text from the model.

        Args:

            text (str): Supplies the prompt to condition on.

            max_length (int): Maximum total length (prompt + generated).

            top_k (int): Number of tokens to consider at each generation step.

            seed (int): Optionally supplies the manual seed to use for the
                generator.  If None, the model's manual seed will be used.

            save_rate (callable): Optionally supplies a callable that will be
                called with the tokens per second rate.

        Returns:

            str: The generated text (including the initial prompt).
        """
        enc = self.enc
        device = self.device
        stop_token = self.stop_token

        # Encode prompt -> tensor of shape (1, T)
        tokens = enc.encode(text)

        x = torch.tensor(
            tokens,
            dtype=torch.long,
            device=device
        ).unsqueeze(0)

        # Create a random generator for reproducibility.
        sample_rng = torch.Generator(device=device)
        if seed is None:
            seed = self.manual_seed
        sample_rng.manual_seed(seed)

        output = []

        # Generate tokens up to our max length, or until we hit the stop token.
        start = time.perf_counter()
        count = 0
        while x.size(1) < max_length:
            count += 1
            with torch.no_grad():
                # Forward pass, ignoring the returned loss.
                (logits, _) = self(x)

            # Take the logits at the last time-step (shape: (1, vocab_size)).
            logits = logits[:, -1, :]

            # Convert to probabilities.
            probs = F.softmax(logits, dim=-1)

            # Top-k sampling.
            topk_probs, topk_indices = torch.topk(probs, k=top_k, dim=-1)

            # Sample the next token.
            next_idx = torch.multinomial(
                topk_probs,
                num_samples=1,
                generator=sample_rng,
            )
            next_token = torch.gather(topk_indices, -1, next_idx)  # (1, 1)

            # If the next token is the stop token, we're done.
            next_token_item = next_token.item()
            if next_token_item == stop_token:
                break

            # Append token to current sequence.  Although we only yield a
            # singular decoded token below, we still need to keep track of
            # the entire sequence for subsequent generation steps.
            x = torch.cat((x, next_token), dim=1)

            # Decode the newly-generated token.
            new_text_fragment = enc.decode([next_token.item()])

            # If the next token isn't printable, terminate generation.  (With
            # our locally-trained GPT2 124M model, this happens quite often.)
            if not all(c in self.printable for c in new_text_fragment):
                break

            output.append(new_text_fragment)

        end = time.perf_counter()
        elapsed = end - start
        tokens_per_sec = float(count) / elapsed
        if save_rate:
            save_rate(tokens_per_sec)

        msg = (
            f'Generated {count} tokens in {elapsed:.2f} seconds '
            f'({tokens_per_sec:.2f} tokens/sec)'
        )
        logging.info(msg)

        return text + ''.join(output)

