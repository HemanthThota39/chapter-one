// Generic Container Apps Job module — used for the analysis worker (queue-triggered)
// and any future workers (PDF render, cron, etc.).

param name string
param location string
param environmentId string
param image string
param managedIdentityId string
@description('Client ID of the managed identity for DefaultAzureCredential.')
param managedIdentityClientId string = ''
param acrLoginServer string
param keyVaultName string

@description('Trigger kind. Queue-triggered jobs use Event type with a scale rule.')
@allowed([ 'Event', 'Manual', 'Schedule' ])
param triggerType string = 'Event'

@description('Service Bus queue name to scale on (only used when triggerType=Event).')
param serviceBusQueueName string = ''

@description('Service Bus namespace hostname (without https://) for the scale rule.')
param serviceBusNamespaceHostname string = ''

@description('CRON expression when triggerType=Schedule.')
param cronExpression string = ''

@description('Max concurrent replicas (parallelism).')
param parallelism int = 1

@description('Max replicas pending at once from a single trigger event.')
param replicaCompletionCount int = 1

@description('Max seconds a replica may run before it is killed.')
param replicaTimeout int = 1800

@description('Max retries per replica.')
param replicaRetryLimit int = 2

@description('Additional environment variables for the container (name/value or name/secretRef).')
param extraEnvVars array = []

@description('Additional secrets (name/keyVaultUrl/identity).')
param extraSecrets array = []

@description('Container command override.')
param command array = []

@description('Container args override.')
param args array = []

// Base secrets every worker gets (DB + app insights)
var baseSecrets = [
  {
    name: 'database-url'
    keyVaultUrl: 'https://${keyVaultName}${environment().suffixes.keyvaultDns}/secrets/postgres-connection-string'
    identity: managedIdentityId
  }
  {
    name: 'appinsights-connection-string'
    keyVaultUrl: 'https://${keyVaultName}${environment().suffixes.keyvaultDns}/secrets/appinsights-connection-string'
    identity: managedIdentityId
  }
  {
    name: 'azure-openai-api-key'
    keyVaultUrl: 'https://${keyVaultName}${environment().suffixes.keyvaultDns}/secrets/azure-openai-api-key'
    identity: managedIdentityId
  }
]

resource job 'Microsoft.App/jobs@2024-03-01' = {
  name: name
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  properties: {
    environmentId: environmentId
    configuration: {
      triggerType: triggerType
      replicaTimeout: replicaTimeout
      replicaRetryLimit: replicaRetryLimit
      // Register the MI at the job level so KEDA scalers can use it to authenticate.
      identitySettings: [
        {
          identity: managedIdentityId
          lifecycle: 'All'
        }
      ]
      eventTriggerConfig: triggerType == 'Event' ? {
        parallelism: parallelism
        replicaCompletionCount: replicaCompletionCount
        scale: {
          minExecutions: 0
          maxExecutions: 5
          pollingInterval: 30
          rules: [
            {
              name: 'azure-servicebus-queue-rule'
              type: 'azure-servicebus'
              identity: managedIdentityId
              metadata: {
                queueName: serviceBusQueueName
                // KEDA's azure-servicebus scaler expects full namespace hostname
                namespace: serviceBusNamespaceHostname
                messageCount: '1'
              }
            }
          ]
        }
      } : null
      scheduleTriggerConfig: triggerType == 'Schedule' ? {
        cronExpression: cronExpression
        parallelism: parallelism
        replicaCompletionCount: replicaCompletionCount
      } : null
      manualTriggerConfig: triggerType == 'Manual' ? {
        parallelism: parallelism
        replicaCompletionCount: replicaCompletionCount
      } : null
      registries: [
        {
          server: acrLoginServer
          identity: managedIdentityId
        }
      ]
      secrets: concat(baseSecrets, extraSecrets)
    }
    template: {
      containers: [
        {
          name: 'worker'
          image: image
          command: empty(command) ? null : command
          args: empty(args) ? null : args
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          env: concat([
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'appinsights-connection-string' }
            { name: 'AZURE_OPENAI_API_KEY', secretRef: 'azure-openai-api-key' }
            { name: 'AZURE_CLIENT_ID', value: managedIdentityClientId }
          ], extraEnvVars)
        }
      ]
    }
  }
}

output id string = job.id
output name string = job.name
