// PostgreSQL Flexible Server — Burstable B1ms, public endpoint + firewall rules.
// Admin password seeded in Key Vault; app connects via password auth for M1-M2.
// (Entra-auth + MI-based passwordless auth can be layered on in Phase 3.)

param location string
param name string
param env string
param logAnalyticsId string
param storageGB int = 32
@secure()
param adminPassword string
param adminLogin string = 'coadmin'
param dbName string = 'chapterone'

resource pg 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: name
  location: location
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '16'
    administratorLogin: adminLogin
    administratorLoginPassword: adminPassword
    storage: {
      storageSizeGB: storageGB
      autoGrow: 'Enabled'
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    network: {
      publicNetworkAccess: 'Enabled'
    }
    authConfig: {
      activeDirectoryAuth: 'Enabled'
      passwordAuth: 'Enabled'
      tenantId: subscription().tenantId
    }
  }
}

resource db 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: pg
  name: dbName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// Firewall: allow access from any Azure service (Container Apps Consumption egress is non-static)
resource fwAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: pg
  name: 'AllowAllAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// In dev only — let the maintainer connect from their laptop to run migrations / ad-hoc queries.
// Not set in prod; prod migrations run via a Container Apps Job inside the Azure network.
resource fwDevAll 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = if (env == 'dev') {
  parent: pg
  name: 'AllowDevAdmin'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '255.255.255.255'
  }
}

resource pgDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-to-la'
  scope: pg
  properties: {
    workspaceId: logAnalyticsId
    logs: [
      { categoryGroup: 'allLogs', enabled: true }
    ]
    metrics: [
      { category: 'AllMetrics', enabled: true }
    ]
  }
}

// Enable common extensions (citext for case-insensitive usernames, pg_trgm for fuzzy search)
resource pgExtensions 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: pg
  name: 'azure.extensions'
  properties: {
    value: 'CITEXT,PG_TRGM,PGCRYPTO'
    source: 'user-override'
  }
}

output fqdn string = pg.properties.fullyQualifiedDomainName
output id string = pg.id
output dbName string = dbName
output adminLogin string = adminLogin
