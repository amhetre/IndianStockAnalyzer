// Single switch for the paid plan. Ads and Pro-only features read from here.
//
// Today every visitor is on the free plan. When the subscription model is added
// (login + Razorpay/Stripe), replace getPlan() with the plan returned by the
// server for the signed-in user — nothing else in the UI needs to change.

export function getPlan() {
  return "free";
}

export const isPro = () => getPlan() === "pro";
