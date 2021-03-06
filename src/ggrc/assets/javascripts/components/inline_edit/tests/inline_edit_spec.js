/*!
  Copyright (C) 2017 Google Inc.
  Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
*/

describe('GGRC.Components.inlineEdit', function () {
  'use strict';

  var Component;  // the component under test

  beforeAll(function () {
    Component = GGRC.Components.get('inlineEdit');
  });

  describe('rendering inline edit for different types', function () {
    var template;
    var frag;
    var types = [
      'checkbox',
      'input',
      'text',
      'dropdown'
    ];

    types.forEach(function (type) {
      it(type + ' component should be rendered', function () {
        template = can.view.mustache('<inline-edit type="' + type + '" />');
        frag = template({});
        frag = $(frag);
        expect(frag.find('inline-' + type).length).toEqual(1);
      });
    });
  });

  describe('component scope methods', function () {
    var $el;
    var ev;
    var scope;

    beforeEach(function () {
      ev = {
        preventDefault: jasmine.createSpy()
      };
      scope = new can.Map({
        context: {},
        instance: {},
        _EV_BEFORE_EDIT: 'before-edit'
      });
    });

    describe('enableEdit() method', function () {
      var enableEdit;
      var $rootEl;  // the component's root element
      var dfdBeforeEdit;

      beforeEach(function () {
        $rootEl = $('<div can-before-edit=""></div>');
        scope.attr('$rootEl', $rootEl);

        dfdBeforeEdit = new can.Deferred();
        spyOn($rootEl, 'triggerHandler')
          .and.returnValue(dfdBeforeEdit.promise());

        enableEdit = Component.prototype.scope.enableEdit;
        enableEdit = enableEdit.bind(scope);
      });

      it('enters the edit mode if editing allowed and no beforeEdit callback',
        function () {
          scope.attr('context.isEdit', false);
          scope.attr('readonly', false);
          $rootEl.attr('can-before-edit', '');

          enableEdit(scope, $el, ev);
          expect(scope.attr('context.isEdit')).toEqual(true);
        }
      );

      it('enters the edit mode if editing allowed and beforeEdit ' +
        'callback\'s promise is resolved',
        function () {
          scope.attr('context.isEdit', false);
          scope.attr('readonly', false);
          $rootEl.attr('can-before-edit', 'open-dialog-foo');

          enableEdit(scope, $el, ev);

          expect(scope.attr('context.isEdit')).toEqual(
            false,
            'Edit mode enabled prematurely.'
          );
          dfdBeforeEdit.resolve();
          expect(scope.attr('context.isEdit')).toEqual(true);
        }
      );

      it('does not enters the edit mode if editing allowed but beforeEdit ' +
        'callback\'s promise is rejected',
        function () {
          scope.attr('context.isEdit', false);
          scope.attr('readonly', false);
          $rootEl.attr('can-before-edit', 'open-dialog-foo');

          enableEdit(scope, $el, ev);

          dfdBeforeEdit.reject();
          expect(scope.attr('context.isEdit')).toEqual(false);
        }
      );

      it('does not enter the edit mode if editing not allowed', function () {
        scope.attr('context.isEdit', false);
        scope.attr('readonly', true);

        enableEdit(scope, $el, ev);
        expect(scope.attr('context.isEdit')).toEqual(false);
      });
    });

    it('onCancel() exits edit mode', function () {
      var onCancel = Component.prototype.scope.onCancel;
      scope.attr('context.isEdit', true);

      onCancel.call(scope, scope, $el, ev);
      expect(scope.attr('context.isEdit')).toEqual(false);
    });
  });

  describe('component init()', function () {
    var scope;
    var instance;
    var method;
    var componentInst;
    var el;
    var options = {};

    beforeAll(function () {
      el = document.createElement('DIV');
      method = Component.prototype.init;
    });
    beforeEach(function () {
      instance = new can.Map({
        title: 'Hello world',
        toggle: true,
        dropdown: ''
      });

      scope = new can.Map({
        instance: instance,
        context: {
          isEdit: false
        }
      });
      componentInst = {
        scope: scope
      };
    });

    describe('sets values custom attribute checkbox', function () {
      beforeEach(function () {
        scope.attr('caId', 123);
        scope.attr('type', 'checkbox');
      });
      it('context.value should be false for 0', function () {
        scope.attr('value', '0');
        method.call(componentInst, el, options);
        expect(scope.attr('context.value')).toEqual(false);
      });
      it('context.value should be true for 1', function () {
        scope.attr('value', '1');
        method.call(componentInst, el, options);
        expect(scope.attr('context.value')).toEqual(true);
      });
    });
    describe('sets values checkbox', function () {
      beforeEach(function () {
        scope.attr('type', 'checkbox');
        scope.attr('property', 'toggle');
      });
      it('context.value should be false', function () {
        scope.attr('instance.toggle', false);
        method.call(componentInst, el, options);
        expect(scope.attr('context.value')).toEqual(false);
      });
      it('context.value should be true', function () {
        scope.attr('instance.toggle', true);
        method.call(componentInst, el, options);
        expect(scope.attr('context.value')).toEqual(true);
      });
    });
    describe('sets values dropdown', function () {
      beforeEach(function () {
        scope.attr('property', 'dropdown');
      });
      it('context.values should be list when string', function () {
        var options = 'a,b,c,d';
        scope.attr('values', options);
        method.call(componentInst, el, options);
        expect(scope.attr('context.values').serialize())
          .toEqual(['a', 'b', 'c', 'd']);
      });
      it('context.values should be list when string', function () {
        var options = ['a', 'b', 'c', 'd'];
        scope.attr('values', options);
        method.call(componentInst, el, options);

        expect(scope.attr('context.values').serialize())
          .toEqual(['a', 'b', 'c', 'd']);
      });
    });
  });
});
