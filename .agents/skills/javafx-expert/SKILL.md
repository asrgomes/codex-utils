---
name: javafx-expert
description: >-
  Use when Codex is implementing, reviewing, testing, or debugging Java 25+ JavaFX applications, especially Maven
  modular apps with JavaFX 25+, Java records in TableView/ListView models, display-dependent integration tests,
  startup/runtime quirks, cursor/focus issues, background Task/Service boundaries, persistence-backed desktop state,
  or JavaFX UI parity against an existing product.
---

# JavaFX Expert

## First Pass

Start by separating three surfaces:

- Model/view-model behavior that should run without a JavaFX display.
- JavaFX control wiring that needs toolkit or scene construction.
- Production startup behavior that needs a real display server.

Prefer view-model tests for workflow logic, then add the smallest JavaFX toolkit or integration test that proves the UI
wiring. Do not assume a green displayless test proves rendered controls, focus, cursor, dialogs, or `TableView` cell
values.

## Java 25+ And Maven

Use the project Maven wrapper and its configured toolchain/profile. For modular JavaFX apps, keep JavaFX dependencies
isolated in the app module; domain, persistence, cache, market-data, strategy, model, and simulation modules should not
depend on JavaFX.

Do:

- Follow the build's configured Java and JavaFX versions; do not upgrade JavaFX only because a newer EA exists.
- Keep JavaFX code at the application boundary and expose plain Java ports/view models from lower modules.
- Use Java 25 language features that are final or enabled by the build. Pattern matching for `switch`, record patterns,
  records, sealed classes, and `var` are good defaults; Java 25 primitive patterns are preview and need build support.

Do not:

- Leak `javafx.*` types into domain, persistence, market-data, strategy, model, simulation, or testkit modules.
- Use JavaFX properties as domain state just to make a `TableView` convenient.
- Turn on preview features silently; require an explicit build/profile decision.

For nullness-checked Java 25 code:

- Keep every package `@NullMarked`.
- Use records for immutable rows/config values and display snapshots, but do not use records for highly editable rows
  that need per-cell observable mutation; use a view model with JavaFX properties there.
- Use `var` for obvious local variables in method bodies, especially JavaFX control construction and test fixtures; keep
  explicit types in public APIs, fields, and places where the type carries meaning.
- Use pattern matching for `instanceof` and `switch` when dispatching on result/error types, instead of manual casts or
  nested `if` chains.
- Treat `Optional`, immutable copies, and explicit empty collections as API boundaries; use `@Nullable` only where null
  is a real semantic state.

Prefer sealed interfaces plus records for small UI state models when a closed set exists:

```java
sealed interface RunMessage {
  record Ready(String text) implements RunMessage {}
  record BadRequest(int status, String body) implements RunMessage {}
  record Failed(String summary) implements RunMessage {}
}

static String userMessage(RunMessage message) {
  return switch (message) {
    case RunMessage.Ready(var text) -> text;
    case RunMessage.BadRequest(var status, var body) -> "Request rejected (" + status + "): " + body;
    case RunMessage.Failed(var summary) -> "Simulation failed: " + summary;
  };
}
```

## TableView And Records

Do not use `PropertyValueFactory` for Java records or refactor-prone modern code. It looks for JavaFX property methods
or JavaBean getters such as `firstNameProperty()`, `getFirstName()`, or `isFirstName()`, not record accessors such as
`firstName()`. The common failure mode is a table with the correct row count and blank cells.

Do:

- Use explicit cell value factories for records, DTOs, and view-model snapshots.
- Use typed extractors so refactors fail at compile time.
- Format non-string fields explicitly at the column boundary.
- Test visible cell values with `getCellObservableValue(...)`, not just `getItems()`.

Do not:

- Use string property names for record components.
- Assume `TableView` row count means rendered cells are populated.
- Use immutable records for cells that users edit in place unless edits are applied by replacing the whole row value.

Use explicit cell value factories:

```java
record StrategyRow(String name, String type, String underlying, int minDtm, int maxDtm) {}

private static <R> TableColumn<R, String> column(String title, Function<R, String> extractor) {
  var column = new TableColumn<R, String>(title);
  column.setCellValueFactory(cell -> new ReadOnlyStringWrapper(extractor.apply(cell.getValue())));
  return column;
}

var nameColumn = column("Name", StrategyRow::name);
var minDtmColumn = column("Min DTM", row -> Integer.toString(row.minDtm()));
```

For non-string record fields, format explicitly in the extractor:

```java
levelColumn("Price", row -> row.price().toPlainString());
levelColumn("Touches", row -> Integer.toString(row.touchCount()));
```

Add tests that inspect rendered column values, not only `table.getItems()`. A useful regression pattern is:

```java
var cells =
    table.getColumns().stream()
        .map(column -> String.valueOf(column.getCellObservableValue(0).getValue()))
        .toList();
assertThat(cells).containsExactly("Name", "Type", "...");
```

## Startup And Cursor

Cursor policy belongs at each top-level JavaFX window/scene boundary, not on whichever control happens to be visible.
Some WSL/Linux desktop paths can otherwise appear to inherit the pointer shape active before the mouse entered the app
window. Dialogs create separate windows/scenes, so the main app `Scene` alone is not enough.

Do:

- Set `scene.setCursor(Cursor.DEFAULT)` for the production stage scene.
- Install the same policy when shell roots are attached to a scene, so factory-created shells are deterministic.
- Install the same policy for every app-owned `Dialog`, because its `DialogPane` is the root of a separate scene.
- Add startup/dialog regression assertions for `scene.getCursor() == Cursor.DEFAULT`.

Do not:

- Assume an unset node cursor is equivalent to a deterministic arrow in every window-manager/display path.
- Treat a root pane cursor as an app-wide policy; it does not cover separate dialog windows.
- Set default cursors on every child control; set the top-level scene default, then override only genuinely special
  controls.

```java
final class AppCursorPolicy {
  private AppCursorPolicy() {}

  static void installDefaultCursor(Stage stage, Scene scene) {
    applyDefaultCursor(scene);
    stage.addEventHandler(WindowEvent.WINDOW_SHOWN, event -> applyDefaultCursor(scene));
  }

  static void installDefaultCursorWhenAttached(Node node) {
    applyDefaultCursor(node.getScene());
    node.sceneProperty().addListener((observable, oldScene, newScene) -> applyDefaultCursor(newScene));
  }

  static void installDefaultCursor(Dialog<?> dialog) {
    var pane = dialog.getDialogPane();
    installDefaultCursorWhenAttached(pane);
    dialog.addEventHandler(DialogEvent.DIALOG_SHOWN, event -> applyDefaultCursor(pane.getScene()));
  }

  private static void applyDefaultCursor(@Nullable Scene scene) {
    if (scene != null) {
      scene.setCursor(Cursor.DEFAULT);
    }
  }
}
```

Add regressions that attach the shell to a `Scene` and assert the scene cursor. Also open a real app dialog and assert
the dialog scene cursor. A root node may keep `getCursor() == null` while the attached scene owns the default.

## Toolkit Lifetime

In integration tests that reuse one JavaFX toolkit for multiple tests, call `Platform.setImplicitExit(false)` before
`Platform.startup(...)`. Otherwise closing the only shown window or dialog can stop the JavaFX runtime and make later
`Platform.runLater` work time out.

Do:

- Initialize the toolkit once per integration-test JVM.
- Use `Platform.setImplicitExit(false)` before `Platform.startup(...)` when tests close windows/dialogs.
- Keep all control creation, scene mutation, and assertions that touch live nodes on the JavaFX Application Thread.
- Use latch-based helpers that fail with useful timeout messages.

Do not:

- Debug repeated `runLater` timeouts by changing production dialog behavior before checking implicit toolkit exit.
- Use arbitrary sleeps as synchronization.
- Flood `Platform.runLater(...)` with many small pending operations; batch UI updates when possible.

Use latch-based helpers for FX work:

- `onFxThread(...)` to run and return values.
- `waitUntilFx(...)` for UI predicates that settle asynchronously.
- Always fail with a useful timeout message rather than sleeping blindly.

When waiting for dialogs to close, tolerate detached scenes/windows:

```java
dialog.getScene() == null
    || dialog.getScene().getWindow() == null
    || !dialog.getScene().getWindow().isShowing()
```

## Display Strategy

Run displayless tests first. JavaFX UI profiles should be opt-in and should use an already available graphical display.
When a JavaFX integration test fails, rerun only the failed test or method. After it passes, run the broader profile.

On WSL/Linux, `xvfb-run` may fail if `/tmp/.X11-unix` cannot be created or if sandbox networking blocks X server
sockets. Do not start Xvfb automatically or make it the default verification path. Use it only when the user or project
explicitly opts in. If Maven fails because it cannot write `~/.m2` metadata from a sandbox, rerun the same Maven command
outside the sandbox instead of changing the build.

Do:

- Keep workflow tests displayless when possible.
- Keep Xvfb opt-in; prefer displayless tests or an existing real `DISPLAY`.
- Run the failed JavaFX test method first while debugging.
- Run the whole JavaFX profile after the narrow fix passes.
- Treat Xvfb failures as environment evidence, not product evidence.

Do not:

- Mark display-dependent UI behavior complete from view-model tests alone.
- Hide a missing display behind skipped tests unless the plan explicitly allows that state.
- Wrap JavaFX UI tests in `xvfb-run` unless the caller explicitly asks for that wrapper.
- Change production UI code just to satisfy a brittle integration-test timing issue.

Useful command shapes:

```bash
./mvnw -pl app-module -am test
./mvnw -pl app-module -am -Pnullability verify
./mvnw -pl app-module -am -Pjavafx-ui-tests \
  -Dit.test='ClassName#methodName' -Dfailsafe.failIfNoSpecifiedTests=false verify
./mvnw -pl app-module -am -Pjavafx-ui-tests verify
```

For final readiness, run full reactor verification, nullability, JavaFX UI profile on a real display when available,
update checks if the project requires them, and `git diff --check`. If no display exists, report
`Unable to open DISPLAY` as environment evidence and do not silently substitute Xvfb.

## Dialogs And Modals

Keep production behavior and test-only stability separate. If a `showAndWait()` dialog causes later tests to hang, first
check test toolkit lifetime before changing production code.

Do:

- Test first cancel, second cancel, `Esc`, and close-window paths for dirty dialogs.
- Treat a detached dialog scene/window as a valid closed state in tests.
- Align help/docs tests with the actual active screen at startup.

Do not:

- Replace `showAndWait()` with modeless behavior only to work around test toolkit shutdown.
- Assert a dialog scene/window remains attached after close.
- Hard-code Simulation help as the startup help context if the app opens Strategies first.

Dirty edit dialogs should test:

- First cancel reports discard guidance and keeps the dialog open.
- Second cancel closes.
- The scene/window can be detached during close.

For contextual help/docs, align tests with the actual initial active screen. If startup opens Strategies, initial
contextual help should load Strategies docs, not Simulation docs, unless product behavior says otherwise.

## Background Work

Keep network and long-running simulation work behind JavaFX `Task`/`Service` or a small binder abstraction. View models
should expose state, status text, and error dialog state without directly owning HTTP clients or platform threads.

Do:

- Keep long-running work off the JavaFX Application Thread.
- Bind UI state to observable worker/view-model state instead of manually pushing every label update.
- Use small adapters around services so view models remain testable without network/display dependencies.

Do not:

- Block the JavaFX Application Thread with HTTP, simulation, file IO, sleeps, or polling loops.
- Update live controls directly from background threads.
- Use `Task`/`Service` as a reason to mix transport, persistence, and UI rendering in one class.

For API errors:

- Preserve HTTP status/body at the transport boundary.
- Surface user-recoverable validation/API 400 failures as dismissible modal state with guidance.
- Keep unexpected/transient failures as persistent status guidance when that matches the product contract.

## Persistence And Startup State

Load settings, templates, and UI state before shell construction. If startup restores a non-default screen, synchronize
both the view model and the visible JavaFX tab. Keep persisted state versioned and migration-friendly; legacy field
names should be normalized on load rather than leaking into UI terminology.

Do:

- Inject or discover data paths before building the production shell.
- Keep tests isolated with temp directories or injectable repositories.
- Normalize legacy persisted names on load, then expose current terminology in the JavaFX UI.

Do not:

- Let tests read or mutate the user's real data directory by default.
- Let legacy persisted field names leak into visible labels, table columns, or help text.
- Restore only the view model state while leaving tabs/controls on the default screen.

For local runtime data, keep tests isolated with temp directories or injectable paths. Do not rely on the user's real
data directory for tests unless the user explicitly asks for a production startup check.

## Source-Backed Checks

- OpenJFX `PropertyValueFactory` looks up JavaFX property methods and JavaBean getters. Record accessors need explicit
  cell value factories.
- JavaFX `Node.cursor` falls back from child to parent to `Scene`; unset node cursors are therefore inherited state, not
  an explicit app default.
- JavaFX `Scene.cursor` is per scene/window; `Dialog.getDialogPane()` is the root of the dialog's visual tree, so
  app-owned dialogs need the same scene-level cursor policy as the primary stage.
- JavaFX `Platform.runLater` runs work on the JavaFX Application Thread and warns against flooding pending runnables;
  long-running operations belong on background threads.
- JavaFX `Service` is designed for background work that interacts with the UI, but its methods/state are intended to be
  used from the JavaFX Application Thread.
- Oracle Java language docs support local variable type inference with judgment and pattern matching/record patterns for
  concise sealed/record-oriented dispatch.

## UI Parity Review Checklist

When porting an existing app to JavaFX, verify all of these explicitly:

- Table rows show real rendered cell values.
- Selection and action buttons behave correctly for empty and non-empty lists.
- Top-level navigation, tabs, menu, toolbar, and footer/status text stay synchronized.
- Help/docs load for the current screen and handle missing docs fixtures predictably.
- Settings save/cancel/reset behavior updates runtime services only after valid save.
- Background runs expose progress, success, API validation failures, and unexpected failures.
- Charts and compact graphical widgets have nonblank rendered content and a tabular fallback if needed.
- Cursor, focus, and modal close behavior are deterministic at startup and after dialogs.
