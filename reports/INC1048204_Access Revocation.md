# Access Revocation

the user account stayed active in the directory after offboarding because the disable workflow failed before revoking group memberships. The root cause was an interrupted IAM job, so the account had to be disabled and every associated permission removed explicitly.

### Remediation

1. Disable the directory account

2. Remove all group and role assignments

3. Invalidate active sessions and tokens

4. Confirm the account is no longer able to authenticate

Disable account and remove memberships
```powershell
Get-ADUser -Identity j.smith | Disable-ADAccount
Get-ADPrincipalGroupMembership j.smith | Remove-ADGroupMember -Members j.smith -Confirm:$false
```

| control | result |
| --- | --- |
| account status | disabled |
| group membership | removed |