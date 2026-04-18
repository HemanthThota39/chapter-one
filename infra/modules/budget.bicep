// Monthly budget + cost alerts at 50%, 75%, 90%
// Scoped to the enclosing resource group.

targetScope = 'resourceGroup'

param env string
param budgetInr int
param contactEmails array

@description('Start of budget window (YYYY-MM-01). Default: first of current month UTC.')
param startDate string = '${utcNow('yyyy-MM')}-01'
param endDate string = '2030-12-31'

resource budget 'Microsoft.Consumption/budgets@2023-05-01' = {
  name: 'co-${env}-monthly'
  properties: {
    category: 'Cost'
    amount: budgetInr
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: startDate
      endDate: endDate
    }
    notifications: {
      pct50: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 50
        thresholdType: 'Actual'
        contactEmails: contactEmails
      }
      pct75: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 75
        thresholdType: 'Actual'
        contactEmails: contactEmails
      }
      pct90: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 90
        thresholdType: 'Actual'
        contactEmails: contactEmails
      }
      forecast: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 100
        thresholdType: 'Forecasted'
        contactEmails: contactEmails
      }
    }
  }
}
