# Stage 2: pool the reduced stage-1 coefficients across départements with multivariate meta-analysis
# (mixmeta, REML), one model per age band. Outputs pooled curves on the percentile scale, BLUP
# département estimates (MMT, RR at 1st/99th percentile) and heterogeneity statistics.
suppressPackageStartupMessages({ library(dlnm); library(mixmeta); library(splines) })

res_dir <- "data/results/dlnm"
red <- readRDS(file.path(res_dir, "stage1_reduced.rds"))
bands <- c("0-64", "65-74", "75-84", "85+")

pooled <- list(); dept_out <- list(); het <- list(); blups <- list()
for (b in bands) {
  items <- Filter(function(x) x$age_band == b, red)
  depts <- vapply(items, `[[`, "", "dept")
  coef  <- t(sapply(items, `[[`, "coef"))
  vcov  <- lapply(items, `[[`, "vcov")
  mv <- mixmeta(coef ~ 1, vcov, method = "reml")
  s  <- summary(mv)
  het[[b]] <- data.frame(age_band = b, n_depts = length(items), I2 = s$i2stat[1], Q = s$qstat$Q[1], Q_pvalue = s$qstat$pvalue[1])

  # Pooled curve on the percentile scale: temperature at each percentile = mean across départements
  tmq  <- rowMeans(sapply(items, `[[`, "tm_q"))
  pcts <- seq(0, 100, 1)
  bvar <- onebasis(tmq, fun = "ns", knots = tmq[c("10%", "75%", "90%")], Boundary.knots = range(tmq))
  cp0  <- crosspred(bvar, coef = coef(mv), vcov = vcov(mv), model.link = "log", at = tmq, cen = tmq["50%"])
  inr  <- pcts >= 1 & pcts <= 99
  mmt_pct <- pcts[inr][which.min(cp0$allRRfit[inr])]
  cp   <- crosspred(bvar, coef = coef(mv), vcov = vcov(mv), model.link = "log", at = tmq, cen = tmq[paste0(mmt_pct, "%")])
  pooled[[b]] <- data.frame(age_band = b, pct = pcts, tm = tmq, rr = cp$allRRfit, lo = cp$allRRlow, hi = cp$allRRhigh, mmt_pct = mmt_pct)

  # BLUPs: each département's curve shrunk toward the pool, on its own temperature scale
  bl <- blup(mv, vcov = TRUE)
  for (i in seq_along(items)) {
    it <- items[[i]]
    grid <- seq(it$tm_range[1], it$tm_range[2], by = 0.1)
    bi <- onebasis(grid, fun = "ns", knots = it$tm_knots, Boundary.knots = it$tm_range)
    c0 <- crosspred(bi, coef = bl[[i]]$blup, vcov = bl[[i]]$vcov, model.link = "log", at = grid, cen = median(grid))
    p1 <- it$tm_q["1%"]; p99 <- it$tm_q["99%"]
    ok <- grid >= p1 & grid <= p99
    mmt <- grid[ok][which.min(c0$allRRfit[ok])]
    ci <- crosspred(bi, coef = bl[[i]]$blup, vcov = bl[[i]]$vcov, model.link = "log", at = grid, cen = mmt)
    at <- function(x) which.min(abs(grid - x))
    dept_out[[paste(it$dept, b)]] <- data.frame(
      dept = it$dept, age_band = b, mmt = mmt, mmt_pct = mean(it$tm_q <= mmt) * 100,
      p1 = p1, rr_p1 = ci$allRRfit[at(p1)], rr_p1_lo = ci$allRRlow[at(p1)], rr_p1_hi = ci$allRRhigh[at(p1)],
      p99 = p99, rr_p99 = ci$allRRfit[at(p99)], rr_p99_lo = ci$allRRlow[at(p99)], rr_p99_hi = ci$allRRhigh[at(p99)],
      tm_mean = mean(it$tm_q))
    blups[[paste(it$dept, b, sep = "|")]] <- list(dept = it$dept, age_band = b, mmt = mmt, coef = bl[[i]]$blup, vcov = bl[[i]]$vcov,
                                                   tm_knots = it$tm_knots, tm_range = it$tm_range)
  }
  cat(sprintf("%-5s pooled over %d départements, MMT at p%d, I2 = %.0f%%\n", b, length(items), mmt_pct, s$i2stat[1]))
}
write.csv(do.call(rbind, pooled),   file.path(res_dir, "pooled_curves.csv"), row.names = FALSE)
write.csv(do.call(rbind, dept_out), file.path(res_dir, "dept_blup_summary.csv"), row.names = FALSE)
write.csv(do.call(rbind, het),      file.path(res_dir, "heterogeneity.csv"), row.names = FALSE)
saveRDS(blups, file.path(res_dir, "stage2_blup.rds"))