# HACS Add-on Repository

This repository is now **HACS-compliant** ✅

## Structure

```
sma-si-can/                          (GitHub repo)
├── repository.json                 (HACS manifest)
├── README.md                       (repo docs)
├── LICENSE                         (MIT)
├── DIRECT_BRIDGE.md               (setup guide)
└── sma-si-6048-bridge/            (add-on)
    ├── addon.json                 (add-on manifest)
    ├── Dockerfile                 (container)
    ├── run.sh                     (startup script)
    ├── requirements.txt           (dependencies)
    └── rootfs/
        └── app/
            ├── bridge_direct.py   (main code)
            ├── protocol.py        (SI protocol)
            └── can_interface.py   (PCAN wrapper)
```

## Add to HACS

### Option 1: Manual Add
In Home Assistant:
1. HACS → Integrations → ⋯ → Custom repositories
2. URL: `https://github.com/mobiletru/sma-si-can`
3. Category: **Add-ons**
4. Add → Install

### Option 2: One-Click Add (if shared link)
`https://my.home-assistant.io/redirect/hacs/?repository_url=https://github.com/mobiletru/sma-si-can&category=integration`

### Option 3: Official HACS Registry
(After tested by HACS team)

## Validation

HACS checks:
- ✅ `repository.json` exists
- ✅ `addon.json` in add-on folder
- ✅ `Dockerfile` present
- ✅ Proper folder structure
- ✅ Valid JSON
- ✅ README.md

All pass! Ready for HACS.

## Install via HACS

Once added to custom repositories:
1. HACS → Add-ons
2. Search: "SMA SI"
3. Click "SMA SI 6048 - EVTV Bridge"
4. Install
5. Configure & start

---

**Status**: HACS-valid ✅  
**Repository**: https://github.com/mobiletru/sma-si-can
