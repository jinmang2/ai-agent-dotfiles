# 새 머신에 세우기

```bash
gh auth login                                  # 1. 먼저. local/ 서브모듈이 이걸 탄다
git clone --recursive https://github.com/jinmang2/ai-agent-dotfiles ~/ai-agent-dotfiles
cd ~/ai-agent-dotfiles && ./install.sh          # 2. 설정 배치 (~/.ssh/config 포함)
source ~/.bashrc
claude                                          # 3. 플러그인 자동 설치 + /login
```

`~/.ssh/config` 는 `install.sh` 가 없을 때만 복사한다(600). 이미 있으면 차이만
보여주고 손대지 않으니, 그때는 직접 합친다.

서브모듈 URL 은 HTTPS 다. 예전엔 SSH 였는데, SSH 키 등록이 이 순서에서 clone 보다
뒤라 서로를 기다리는 교착이 있었다. HTTPS 는 `gh auth git-credential` 로
비공개 저장소도 clone·push 가 되므로 `gh auth login` 하나만 먼저 하면 된다.

`--recursive` 를 빠뜨렸으면 `git submodule update --init`. 서브모듈이 비어 있어도
`install.sh` 는 정상 동작한다 — 머신 고유 오버레이와 `ssh-config` 만 빠진다.

## 확인

| 명령 | 봐야 할 것 |
|---|---|
| `./install.sh --check` | 링크가 전부 `ok` |
| `claude-accounts` | 계정별 로그인 · 공유 링크가 `정상` |
| `claude doctor` | 설치 건강성 |
| `tmux ls` | 세션이 뜨는지 |
| tmux 안에서 `cd ~/어떤저장소` | 창 이름이 저장소 이름으로 바뀌는지 (상태줄 기호 없음) |
| 그 창에서 `claude` 실행 | 상태줄에 `»` 기호·번호 배경색이 붙는지, 종료하면 다시 빠지는지 |
| `python3 scripts/test-merge-settings.py` | 28개 통과 |

창 이름이 안 붙으면 tmux 밖이거나 `automatic-rename` 이 켜져 있는 것이다.
훅 자체는 이렇게 직접 찔러본다:

```bash
printf '{"cwd":"%s"}' "$PWD" | agent-window-label '' busy && tmux display -p '#{window_name} @cc=#{@cc}'
```

## git 신원

저장소에 두지 않는다. `~/.gitconfig` 는 `gh auth` 와 `git config --global` 이 수시로
다시 쓰기 때문에 심링크로 걸면 끊긴다.

```bash
git config --global user.name  "<이름>"
git config --global user.email "<이메일>"
```

## 저장소에 없어서 매번 다시 하는 것

SSH 키 (`ssh-keygen` → `gh ssh-key add`) · gh · Claude · Codex 로그인.
언어/런타임 환경(conda·nvm·CUDA)은 프로젝트 소유다.

프레임워크는 재설치로 복원한다 — 저장소에 담지 않는다:

```bash
npm i -g oh-my-claude-sisyphus && omc setup                                # OMC CLI
npm i -g @openai/codex oh-my-codex && omx setup                            # Codex + OMX
uv tool install basedpyright                                               # lsp_* 12개
git clone https://github.com/garrytan/gstack.git ~/.claude/skills/gstack   # 선택 (1.5G)
```

**`omc` CLI 는 플러그인과 별개로 깔린다.** 플러그인만 올리면 CLI 가 옛 버전에 남고,
그 상태로 `omc setup` 을 돌리면 옛 `CLAUDE.md` 를 쓴다. 두 버전이 어긋나면
`./install.sh --check` 가 알려준다.

**`basedpyright` 는 `shell/agents.sh` 가 이름으로 가리킨다** (`OMC_PYTHON_LSP`).
안 깔면 OMC 의 `lsp_*` 12개가 전부 설치 힌트만 반환하고 조용히 죽는다.
이것도 `--check` 가 잡는다. 자세한 건 `docs/omc.md`.

`~/.claude/hud/` 는 반쯤 다르다 — 저장소에 원본은 없지만, OMC 플러그인이 깔리고 나면
`install.sh` 가 마켓플레이스 클론에서 5개 파일을 복사해준다. 그래서 `claude` 를 한 번
띄운 뒤 `./install.sh` 를 다시 돌리는 순서가 된다. 그전까지 스테이터스라인이 비어
보이는 건 정상이다. `omc setup` 은 OMC 버전을 올린 뒤에 돌린다 — HUD 와 `CLAUDE.md` 를 새 버전에 맞춘다.

`omc setup` 을 꺼릴 이유는 없다. `~/.claude/CLAUDE.md` 도 여기 속한다. `<!-- OMC:START -->` … `<!-- OMC:END -->` 사이는
OMC 소유이고 `omc setup` 이 그 블록만 갈아끼운다 (`<!-- OMC:VERSION:... -->` 표시가
있다). 바깥에 쓴 개인 지침은 `<!-- User customizations -->` 아래로 보존되고, 매번
`CLAUDE.md.backup.<타임스탬프>` 가 남는다. 즉 덮어쓰기가 아니라 우리 `.bashrc`
블록과 같은 센티넬 병합이다.
