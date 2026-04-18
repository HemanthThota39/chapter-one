# Infrastructure — Bicep + Azure

All Azure resources deployed via Bicep. See `docs/phase2/06-infrastructure.md` for the full spec.

## Layout

```
infra/
├── main.bicep                    # top-level deployment
├── modules/                       # reusable modules
│   ├── network.bicep
│   ├── identity.bicep
│   ├── container-apps-env.bicep
│   ├── container-app-api.bicep
│   ├── container-app-job.bicep
│   ├── postgres.bicep
│   ├── storage.bicep
│   ├── service-bus.bicep
│   ├── key-vault.bicep
│   ├── acr.bicep
│   ├── monitor.bicep
│   ├── static-web-app.bicep
│   └── budget.bicep
├── envs/
│   ├── dev.parameters.json
│   └── prod.parameters.json
└── scripts/
    ├── deploy-dev.sh
    ├── deploy-prod.sh
    └── teardown-dev.sh
```

## Local deployment (dev)

```bash
az login
az group create -n co-dev-rg-cin -l centralindia
az deployment group create \
  -g co-dev-rg-cin \
  -f infra/main.bicep \
  -p @infra/envs/dev.parameters.json
```

## CI deployment

See `.github/workflows/deploy-dev.yml` and `deploy-prod.yml`.

## Validating changes

```bash
az deployment group what-if \
  -g co-dev-rg-cin \
  -f infra/main.bicep \
  -p @infra/envs/dev.parameters.json
```

PRs touching `infra/**` automatically run `infra-validate.yml` which posts the what-if output as a PR comment.
