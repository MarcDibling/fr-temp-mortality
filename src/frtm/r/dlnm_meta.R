# Stage-2 meta-regression: does a département-level predictor explain the between-département
# variation in the temperature-mortality curve? One mixmeta per predictor per age band (Wald test
# on the 4 coefficients of the reduced curve), then a multivariable model, then predicted curves
# at the 25th and 75th percentile of each predictor for the 85+ band.
suppressPackageStartupMessages({ library(dlnm); library(mixmeta); library(splines) })
res_dir <- "data/results/dlnm"
red <- readRDS(file.path(res_dir, "stage1_reduced.rds"))
cov <- read.csv("data/reference/dept_covariates.csv", colClasses = c(dept = "character"))
preds <- c("tm_mean", "tm_sd", "share_85plus", "log_density", "urban_share", "lat", "coastal")
bands <- c("0-64", "65-74", "75-84", "85+")

wald <- function(mv, pred) {
  idx <- grep(paste0("\\.", pred, "$"), names(coef(mv)))
  b <- coef(mv)[idx]; V <- vcov(mv)[idx, idx]
  w <- as.numeric(t(b) %*% solve(V) %*% b)
  c(wald = w, df = length(idx), p = pchisq(w, length(idx), lower.tail = FALSE))
}

rows <- list(); curves <- list()
for (b in bands) {
  items <- Filter(function(x) x$age_band == b, red)
  depts <- vapply(items, `[[`, "", "dept")
  coef  <- t(sapply(items, `[[`, "coef")); vcov <- lapply(items, `[[`, "vcov")
  X <- cov[match(depts, cov$dept), ]
  m0 <- mixmeta(coef ~ 1, vcov, method = "reml")
  i2_0 <- summary(m0)$i2stat[1]
  for (p in preds) {
    m1 <- mixmeta(as.formula(paste("coef ~", p)), vcov, data = X, method = "reml")
    w <- wald(m1, p)
    rows[[paste(b, p)]] <- data.frame(age_band = b, model = "univariable", predictor = p, wald = w["wald"], df = w["df"], p_value = w["p"],
                                      I2_before = i2_0, I2_after = summary(m1)$i2stat[1], AIC = AIC(m1))
  }
  mm <- mixmeta(coef ~ tm_mean + share_85plus + urban_share + coastal, vcov, data = X, method = "reml")
  for (p in c("tm_mean", "share_85plus", "urban_share", "coastal")) {
    w <- wald(mm, p)
    rows[[paste(b, "multi", p)]] <- data.frame(age_band = b, model = "multivariable", predictor = p, wald = w["wald"], df = w["df"], p_value = w["p"],
                                               I2_before = i2_0, I2_after = summary(mm)$i2stat[1], AIC = AIC(mm))
  }
  # Predicted curves at the 25th/75th percentile of each predictor, other predictors at their mean
  tmq <- rowMeans(sapply(items, `[[`, "tm_q")); pcts <- 0:100
  bvar <- onebasis(tmq, fun = "ns", knots = tmq[c("10%", "75%", "90%")], Boundary.knots = range(tmq))
  for (p in c("tm_mean", "share_85plus", "urban_share")) {
    for (q in c(0.25, 0.75)) {
      nd <- as.data.frame(t(colMeans(X[, c("tm_mean", "share_85plus", "urban_share", "coastal")])))
      nd[[p]] <- quantile(X[[p]], q)
      pr <- predict(mm, newdata = nd, vcov = TRUE)
      cp <- crosspred(bvar, coef = pr$fit, vcov = pr$vcov, model.link = "log", at = tmq, cen = tmq["88%"])
      curves[[paste(b, p, q)]] <- data.frame(age_band = b, predictor = p, quantile = q, value = nd[[p]], pct = pcts, rr = cp$allRRfit, lo = cp$allRRlow, hi = cp$allRRhigh)
    }
  }
  cat(sprintf("%-5s I2 intercept-only %.0f%%, multivariable %.0f%%\n", b, i2_0, summary(mm)$i2stat[1]))
}
out <- do.call(rbind, rows); rownames(out) <- NULL
write.csv(out, file.path(res_dir, "meta_regression.csv"), row.names = FALSE)
write.csv(do.call(rbind, curves), file.path(res_dir, "meta_curves.csv"), row.names = FALSE)
print(out[out$model == "univariable", c("age_band", "predictor", "p_value", "I2_before", "I2_after")], digits = 3)