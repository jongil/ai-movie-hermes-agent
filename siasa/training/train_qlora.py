"""Unsloth QLoRA fine-tune: gemma4-12b → 시사베테랑 작가 (로컬 16GB).

- 학습쌍: train.jsonl (system 페르소나 + user 주제 → assistant 원본 대본).
- completion-only: 프롬프트(system+user) 마스킹, 대본(assistant)만 loss → 생성 학습.
- LoRA r16, seq 8192. 산출 = LoRA 어댑터.
- EPOCHS / LORA_OUT env로 조정(기본 3ep, siasa_lora).

실행(호스트, GPU 유휴 시):
  EPOCHS=6 LORA_OUT=/.../siasa_lora_e6 LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu ~/unsloth-venv/bin/python train_qlora.py
"""
import os
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
from unsloth import FastModel
import torch
from datasets import load_dataset
from trl import SFTTrainer, SFTConfig
from unsloth.chat_templates import train_on_responses_only

BASE = os.environ.get("HERMES_DIR", "/home/gdash86/project/ai-movie-hermes-agent")
MODEL = "unsloth/gemma-4-12b-it"
MAXSEQ = 8192
EPOCHS = float(os.environ.get("EPOCHS", "3"))
LORA_OUT = os.environ.get("LORA_OUT", f"{BASE}/siasa_lora")

model, tok = FastModel.from_pretrained(
    model_name=MODEL, max_seq_length=MAXSEQ, load_in_4bit=True, full_finetuning=False,
)
model = FastModel.get_peft_model(
    model, r=16, lora_alpha=32, lora_dropout=0, bias="none",
    finetune_vision_layers=False, finetune_language_layers=True,
    finetune_attention_modules=True, finetune_mlp_modules=True, random_state=42,
)

ds = load_dataset("json", data_files=f"{BASE}/train.jsonl", split="train")

def fmt(ex):
    return {"text": tok.apply_chat_template(ex["messages"], tokenize=False, add_generation_prompt=False)}

ds = ds.map(fmt, remove_columns=ds.column_names)

trainer = SFTTrainer(
    model=model, tokenizer=tok, train_dataset=ds,
    args=SFTConfig(
        dataset_text_field="text", max_seq_length=MAXSEQ,
        per_device_train_batch_size=1, gradient_accumulation_steps=4,
        warmup_steps=5, num_train_epochs=EPOCHS, learning_rate=2e-4,
        logging_steps=1, optim="adamw_8bit", weight_decay=0.01,
        lr_scheduler_type="linear", seed=42,
        output_dir=f"{BASE}/qlora_out", report_to="none",
    ),
)
trainer = train_on_responses_only(
    trainer, instruction_part="<|turn>user\n", response_part="<|turn>model\n",
)

stats = trainer.train()
print("EPOCHS=", EPOCHS)
print("train_runtime_sec=", stats.metrics.get("train_runtime"))
print("train_loss=", stats.metrics.get("train_loss"))
model.save_pretrained(LORA_OUT)
tok.save_pretrained(LORA_OUT)
print("SAVED_LORA=", LORA_OUT)
