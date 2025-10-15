package iam.rules

# Deny wildcard actions unless explicitly allowed
deny[msg] {
  input.policy.Statement[_].Action == "*"
  msg := "Action:* detected – use least-privilege explicit actions"
}

# Require ExternalId for external principals
deny[msg] {
  s := input.trust
  s.Principal.AWS != null
  not startswith(s.Principal.AWS, "arn:aws:iam::${ORG_ACCOUNT_PREFIX}")
  not s.Condition.StringEquals["sts:ExternalId"]
  msg := "External principal without ExternalId condition"
}

# Forbid iam:PassRole without resource scoping
deny[msg] {
  some i
  st := input.policy.Statement[i]
  action_is(st.Action, "iam:PassRole")
  st.Resource == "*"
  msg := "iam:PassRole must be scoped to specific role ARNs"
}

# Forbid sts:AssumeRole* on * unless conditions restrict by external ID or source
deny[msg] {
  some i
  st := input.policy.Statement[i]
  action_is(st.Action, "sts:AssumeRole")
  st.Resource == "*"
  not st.Condition
  msg := "sts:AssumeRole on * requires restrictive Condition"
}
deny[msg] {
  some i
  st := input.policy.Statement[i]
  action_is(st.Action, "sts:AssumeRoleWithWebIdentity")
  st.Resource == "*"
  not st.Condition
  msg := "sts:AssumeRoleWithWebIdentity on * requires restrictive Condition"
}

# Require condition on s3:PutObject if bucket is public-write suspect (defense-in-depth)
deny[msg] {
  some i
  st := input.policy.Statement[i]
  action_is(st.Action, "s3:PutObject")
  st.Resource == "*"
  not st.Condition.StringEquals["s3:x-amz-server-side-encryption"]
  msg := "s3:PutObject must enforce SSE via condition"
}

# Enforce tag on created roles/policies (example metadata gate)
warn[msg] {
  input.metadata.missing_tags
  msg := "Resource missing required tags (Owner, CostCenter)"
}

# helper: check if action field (string or array) includes an action exactly
action_is(action, name) {
  is_string(action)
  action == name
}
action_is(action, name) {
  some i
  is_array(action)
  action[i] == name
}
