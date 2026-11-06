# Attributable deaths from the stage-2 BLUP curves, forward perspective (Gasparrini & Leone 2014):
#   for each day t, AF(t) = 1 - exp(-logRR(tm_t)), applied to the mean deaths over days t..t+21.
# Split: cold (tm < MMT) vs heat (tm > MMT); moderate (within 2.5-97.5th pct) vs extreme (beyond).
# Uncertainty: 500 draws of the BLUP coefficients from N(coef, vcov); empirical 95% intervals.
# Covid months (Mar 2020 - Jun 2021) excluded from the sums. Period: 2000-2025.
suppressPackageStartupMessages({ library(arrow); library(dplyr); library(dlnm); library(MASS) })
set.seed(2026)
res_dir <- "data/results/dlnm"
blups <- readRDS(file.path(res_dir, "stage2_blup.rds"))
NSIM <- 500; LAG <- 21

panel <- open_dataset("data/gold/panel.parquet") |>
  filter(date >= as.Date("2000-01-01"), date <= as.Date("2025-12-31")) |>
  dplyr::select(date, dept, age_band, deaths, tm) |>
  collect() |>
  group_by(date, dept, age_band) |>
  summarise(deaths = sum(deaths), tm = first(tm), .groups = "drop") |>
  arrange(dept, age_band, date)

fwd_mean <- function(y, L) {   # mean of y[t..t+L], NA where the window runs past the end
  n <- length(y); cs <- c(0, cumsum(y)); out <- rep(NA_real_, n)
  idx <- 1:(n - L); out[idx] <- (cs[idx + L + 1] - cs[idx]) / (L + 1); out
}

by_cell <- list(); by_year <- list()
for (key in names(blups)) {
  bl <- blups[[key]]
  d <- panel |> filter(dept == bl$dept, age_band == bl$age_band)
  if (nrow(d) == 0) next
  keep <- !(d$date >= as.Date("2020-03-01") & d$date <= as.Date("2021-06-30")) & !is.na(d$tm)
  basis <- onebasis(d$tm, fun = "ns", knots = bl$tm_knots, Boundary.knots = bl$tm_range)
  cen   <- onebasis(bl$mmt, fun = "ns", knots = bl$tm_knots, Boundary.knots = bl$tm_range)
  Bc <- sweep(basis, 2, as.vector(cen))             # centred basis: logRR = Bc %*% coef
  Bc[is.na(Bc)] <- 0
  ybar <- fwd_mean(d$deaths, LAG)
  q <- quantile(d$tm, c(.025, .975), na.rm = TRUE)
  side <- ifelse(d$tm < bl$mmt, "cold", "heat")
  extreme <- d$tm < q[1] | d$tm > q[2]
  comp <- paste0(side, ifelse(extreme, "_extreme", "_moderate"))
  coefs <- rbind(bl$coef, mvrnorm(NSIM, bl$coef, bl$vcov))        # row 1 = point estimate
  an <- (1 - exp(-(Bc %*% t(coefs)))) * ybar                       # days x (1 + NSIM)
  an[!keep | is.na(ybar), ] <- 0
  year <- as.integer(format(d$date, "%Y"))
  tot_deaths <- sum(d$deaths[keep])
  for (cmp in c("cold_moderate", "cold_extreme", "heat_moderate", "heat_extreme")) {
    s <- colSums(an[which(comp == cmp), , drop = FALSE])
    by_cell[[paste(key, cmp)]] <- data.frame(dept = bl$dept, age_band = bl$age_band, component = cmp,
      an = s[1], lo = quantile(s[-1], .025), hi = quantile(s[-1], .975), deaths = tot_deaths)
  }
  for (sd in c("cold", "heat")) {
    sel <- which(side == sd); m <- an[sel, 1]; yy <- year[sel]
    by_year[[paste(key, sd)]] <- data.frame(dept = bl$dept, age_band = bl$age_band, side = sd,
      year = sort(unique(yy)), an = tapply(m, yy, sum))
  }
  cat(sprintf("%s %-5s cold %.0f heat %.0f of %d deaths\n", bl$dept, bl$age_band,
              sum(an[which(side == "cold"), 1]), sum(an[which(side == "heat"), 1]), tot_deaths))

}
write.csv(do.call(rbind, by_cell), file.path(res_dir, "attributable_by_cell.csv"), row.names = FALSE)
write.csv(do.call(rbind, by_year), file.path(res_dir, "attributable_by_year.csv"), row.names = FALSE)