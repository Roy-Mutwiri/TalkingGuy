# Sources and public datasets

Checked 2026-10-26. External datasets are not included in this archive.

1. LiveChat, official repository: https://github.com/gaojingsheng/LiveChat
   Dataset format: https://github.com/gaojingsheng/LiveChat/blob/master/Dataset/README.md
   Paper: https://aclanthology.org/2023.acl-long.858/
   Chinese streamer/audience dialogues and addressee recognition. Useful interaction structure, not an English top-streamer voice dataset. Repository-level software licensing must not be assumed to resolve every source-media use.

2. TwitchChat, research paper: https://ojs.aaai.org/index.php/AIIDE/article/view/7439
   Data distribution: https://huggingface.co/datasets/Michielo/twitchchat
   Audience chat data, useful for chat understanding. Viewer comments alone do not teach host replies, vocal delivery or response timing. Verify data terms for your intended use.

3. OpenAssistant OASST1: https://huggingface.co/datasets/OpenAssistant/oasst1
   Human-written, rated assistant-style conversations; Apache 2.0 dataset card. Optional short-answer supplement, not a streamer-specific corpus. A capable instruction model may already have adequate general conversational training.

4. Response-worthy chat research: https://aclanthology.org/2024.sigdial-1.16/
   Studies contextual relevance, topic uniqueness and sentiment-related criteria for selecting chats. This is evidence for a selection problem, not proof of increased watch time in your stream.

5. Live-Aid: https://aclanthology.org/2026.findings-acl.1193/
   Chinese multimodal interleaved livestream interactions. Later research option if audio/video temporal reasoning is needed. Dataset access and commercial terms were not established in this pack.

6. InteracVid: https://huggingface.co/datasets/Holomorphica/InteracVid-Parquet
   Paper: https://arxiv.org/html/2608.01157v1
   Context/query/response material for interactive audio-video research, with real and synthetic query sources visible in the data card. Later research option, not a ready drop-in text-to-speech or English retention dataset. Dataset/source-media commercial terms were not verified; the paper's license is not automatically the dataset's license.

7. Hugging Face TRL SFT: https://huggingface.co/docs/trl/en/sft_trainer
   Supports conversational and prompt-completion fine-tuning formats.

8. Hugging Face TRL DPO: https://huggingface.co/docs/trl/en/dpo_trainer
   Uses preferred/rejected completions for the same prompt. The included preference files follow the conversational pattern; inspect compatibility with your installed version.

9. Chatterbox: https://github.com/resemble-ai/chatterbox
   The official Turbo documentation describes native paralinguistic cues. This does not establish that every local installation supports all cues or that your training pipeline is ready.

## Provenance of the included examples

All included examples and preference labels are original synthetic material authored for this task. They are not scraped comments, quotations, or recordings of named streamers. No real viewer results, private histories or real-time market data are claimed. The set is model-checked for structure, not independently human-reviewed. The intended use is as a starting point for Roy's own training and evaluation workflow.
